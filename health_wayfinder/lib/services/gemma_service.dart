import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show MethodChannel, rootBundle;
import 'package:http/http.dart' as http;
import 'package:llama_cpp_dart/llama_cpp_dart.dart';
import 'package:path_provider/path_provider.dart';

/// Backend the chat methods route to.
///
/// - [ollama]: POSTs to an OpenAI-compatible /v1/chat/completions endpoint
///   on the host. Used by the iOS Simulator, macOS, web, and dev workflows.
/// - [device]: on-device llama.cpp via `llama_cpp_dart` 0.9.0-dev.6 +
///   `llama.xcframework` (Apple Metal). Used on real iOS hardware.
enum GemmaMode { ollama, device }

class GemmaService {
  static final GemmaService _instance = GemmaService._();
  static GemmaService get instance => _instance;
  GemmaService._();

  // ============================================================
  // Mode selection. Default ollama. To run on-device on a real iPhone:
  //   flutter run --dart-define=GEMMA_MODE=device
  // ============================================================
  static const _modeRaw =
      String.fromEnvironment('GEMMA_MODE', defaultValue: 'ollama');

  static GemmaMode get mode =>
      _modeRaw == 'device' ? GemmaMode.device : GemmaMode.ollama;

  // Ollama / OpenAI-compatible endpoint config. Match training/.env defaults.
  static const _ollamaBaseUrl = String.fromEnvironment(
    'OLLAMA_URL',
    defaultValue: 'http://127.0.0.1:11434/v1',
  );
  static const _ollamaModel = String.fromEnvironment(
    'OLLAMA_MODEL',
    defaultValue: 'medical-wayfinder-gemma-4-e2b',
  );
  static const _ollamaApiKey = String.fromEnvironment(
    'OLLAMA_API_KEY',
    defaultValue: 'not-needed',
  );

  /// Memoized init future. Cleared back to null on failure so callers can
  /// retry (e.g. after a transient asset-copy error).
  Future<void>? _initFuture;

  /// Memoized createSession future. Set whenever createSession starts;
  /// callers (sendMessage, closeSession) await this before touching chat
  /// state so an in-flight session prime can't race against a request.
  Future<void>? _sessionFuture;

  /// Marks an in-flight sendMessage/stream. createSession, closeSession,
  /// and shutdown await this Completer before disposing the EngineChat or
  /// LlamaEngine — disposing those while a native generate is still
  /// pumping tokens is a use-after-free on the llama.cpp FFI boundary.
  Completer<void>? _pendingGeneration;

  bool _modelReady = false;

  // Device state.
  LlamaEngine? _engine;
  EngineChat? _chat;

  /// Asset path of the GGUF (Q4_K_M Gemma 4 E2B-IT). Passed through to our
  /// native AppDelegate bridge.
  static const _deviceGgufAsset = 'assets/models/model.gguf';
  static const _deviceGgufFilename = 'model.gguf';

  /// Ollama in-memory history.
  final List<Map<String, String>> _ollamaMessages = [];

  bool get isReady => _modelReady;

  /// Idempotent. The first call starts initialization; subsequent calls
  /// while the first is in flight await the same future. On failure the
  /// memoized future is cleared so the next call retries from scratch.
  Future<void> init() {
    final existing = _initFuture;
    if (existing != null) return existing;
    final future = _doInit();
    _initFuture = future;
    return future.catchError((Object e, StackTrace st) {
      _initFuture = null;
      // Propagate the original error to the caller.
      throw e;
    });
  }

  Future<void> _doInit() async {
    switch (mode) {
      case GemmaMode.ollama:
        _modelReady = true;
        debugPrint(
            '[GemmaService] Initialized (ollama @ $_ollamaBaseUrl, model $_ollamaModel)');
        return;
      case GemmaMode.device:
        debugPrint('[GemmaService] Device init start');
        final path = await _ensureGgufOnDisk();
        final f = File(path);
        final exists = await f.exists();
        final size = exists ? await f.length() : 0;
        debugPrint(
            '[GemmaService] GGUF check: exists=$exists size=$size bytes path=$path');
        if (!exists || size < 3000000000) {
          if (exists) await f.delete();
          throw StateError(
              'GGUF at $path missing or truncated (size=$size). Delete and re-run.');
        }
        debugPrint('[GemmaService] Spawning LlamaEngine (Metal GPU)');
        _engine = await LlamaEngine.spawnFromProcess(
          modelParams: ModelParams(path: path, gpuLayers: 99),
          contextParams: const ContextParams(
            nCtx: 4096,
            nBatch: 4096,
            nUbatch: 512,
          ),
        );
        _modelReady = true;
        debugPrint('[GemmaService] LlamaEngine ready');
        return;
    }
  }

  static const _assetCopyChannel =
      MethodChannel('health_wayfinder/asset_copy');

  Future<String> _ensureGgufOnDisk() async {
    final docs = await getApplicationDocumentsDirectory();
    final target = '${docs.path}/$_deviceGgufFilename';
    final f = File(target);
    if (await f.exists()) {
      final size = await f.length();
      if (size > 3000000000) {
        debugPrint('[GemmaService] GGUF already on disk ($size bytes)');
        return target;
      }
      debugPrint('[GemmaService] GGUF truncated (size=$size), re-copying');
      await f.delete();
    }
    debugPrint('[GemmaService] Copying GGUF asset → $target (~3.2 GB, one-time)');
    final result = await _assetCopyChannel.invokeMapMethod<String, Object?>(
      'copyAsset',
      {'assetKey': _deviceGgufAsset, 'targetPath': target},
    );
    final size = result?['size'] as int? ?? -1;
    debugPrint('[GemmaService] GGUF copy complete: $size bytes');
    return target;
  }

  Future<void> downloadModel({
    void Function(double progress)? onProgress,
    String? huggingFaceToken,
  }) async {
    for (var i = 0; i <= 10; i++) {
      await Future.delayed(const Duration(milliseconds: 200));
      onProgress?.call(i / 10);
    }
    _modelReady = true;
  }

  Future<bool> isModelInstalled() async => true;

  static const _maxHistoryPairs = 4;

  /// Create a chat session. For ollama this seeds the system message; for
  /// device this disposes the prior EngineChat (after waiting for any
  /// in-flight generation) and creates a fresh one seeded with the system
  /// prompt.
  Future<void> createSession({int maxTokens = 2048}) {
    final future = _doCreateSession();
    _sessionFuture = future;
    return future.catchError((Object e, StackTrace st) {
      _sessionFuture = null;
      throw e;
    });
  }

  Future<void> _doCreateSession() async {
    // Wait for any in-flight generation to finish before we touch _chat.
    final pending = _pendingGeneration;
    if (pending != null) {
      try {
        await pending.future;
      } catch (_) {/* the generation's own failure isn't our concern */}
    }
    final systemPrompt = await _loadSystemPromptTemplate();
    switch (mode) {
      case GemmaMode.ollama:
        _ollamaMessages
          ..clear()
          ..add({'role': 'system', 'content': systemPrompt});
        debugPrint('[GemmaService] Ollama session created '
            '(${systemPrompt.length} chars static system prompt)');
        return;
      case GemmaMode.device:
        if (_engine == null) {
          throw StateError('Engine not initialized. Call init() first.');
        }
        // Tear down any previous chat so the model's embedded chat template
        // renders cleanly from the new system message.
        await _chat?.dispose();
        _chat = await _engine!.createChat();
        _chat!.addSystem(systemPrompt);
        debugPrint('[GemmaService] Device chat session created '
            '(${systemPrompt.length} chars system prompt)');
        return;
    }
  }

  /// Send a message and get a complete response. The [contextBlock]
  /// (orchestrator slot state) is wrapped into the user turn so the static
  /// system prompt stays cacheable across turns.
  ///
  /// Awaits any in-flight session prime (so the orchestrator can dispatch
  /// queries before init/createSession is complete without throwing).
  /// Wraps the device-mode generate in a try-block that registers a
  /// pending-generation Completer so createSession/closeSession/shutdown
  /// can serialize against it.
  Future<String> sendMessage(
    String userMessage, {
    String? contextBlock,
  }) async {
    // Ensure init + session are done before we touch any chat state.
    final initF = _initFuture;
    if (initF != null) await initF;
    final sessionF = _sessionFuture;
    if (sessionF != null) await sessionF;

    final wrapped = contextBlock == null || contextBlock.isEmpty
        ? userMessage
        : 'CONTEXT:\n$contextBlock\n\nUSER: $userMessage';
    switch (mode) {
      case GemmaMode.ollama:
        return _ollamaSendMessage(wrapped);
      case GemmaMode.device:
        final chat = _chat;
        if (chat == null) {
          throw StateError('No active session. Call createSession first.');
        }
        final completer = Completer<void>();
        _pendingGeneration = completer;
        try {
          chat.addUser(wrapped);
          final buf = StringBuffer();
          await for (final event in chat.generate(
            sampler: const SamplerParams(
              temperature: 0.4,
              topP: 0.95,
              topK: 40,
            ),
            maxTokens: 1024,
            // The GGUF's embedded chat template is a Jinja macro that
            // llama.cpp's `llama_chat_apply_template` doesn't recognize.
            // Override with the Gemma-family hint so llama.cpp's built-in
            // Gemma renderer applies `<start_of_turn>...<end_of_turn>`.
            templateOverride: KnownChatTemplates.gemma,
          )) {
            if (event is TokenEvent) buf.write(event.text);
          }
          return buf.toString();
        } finally {
          completer.complete();
          if (identical(_pendingGeneration, completer)) {
            _pendingGeneration = null;
          }
        }
    }
  }

  Stream<String> sendMessageStream(String userMessage) async* {
    final initF = _initFuture;
    if (initF != null) await initF;
    final sessionF = _sessionFuture;
    if (sessionF != null) await sessionF;

    switch (mode) {
      case GemmaMode.ollama:
        yield await _ollamaSendMessage(userMessage);
        return;
      case GemmaMode.device:
        final chat = _chat;
        if (chat == null) {
          throw StateError('No active session. Call createSession first.');
        }
        final completer = Completer<void>();
        _pendingGeneration = completer;
        try {
          chat.addUser(userMessage);
          await for (final event in chat.generate(
            sampler: const SamplerParams(
              temperature: 0.4,
              topP: 0.95,
              topK: 40,
            ),
            maxTokens: 1024,
            templateOverride: KnownChatTemplates.gemma,
          )) {
            if (event is TokenEvent) yield event.text;
          }
          return;
        } finally {
          completer.complete();
          if (identical(_pendingGeneration, completer)) {
            _pendingGeneration = null;
          }
        }
    }
  }

  Future<String> sendMessageWithImage({
    required String userMessage,
    required List<int> imageBytes,
  }) async {
    if (mode == GemmaMode.ollama) {
      return _ollamaSendMessage(userMessage);
    }
    return sendMessage(userMessage);
  }

  /// Close just the chat session. Use when the user resets the
  /// conversation but the app is still alive (e.g. Start Over).
  Future<void> closeSession() async {
    final pending = _pendingGeneration;
    if (pending != null) {
      try {
        await pending.future;
      } catch (_) {/* ignore */}
    }
    switch (mode) {
      case GemmaMode.ollama:
        _ollamaMessages.clear();
        return;
      case GemmaMode.device:
        await _chat?.dispose();
        _chat = null;
        _sessionFuture = null;
        return;
    }
  }

  /// Tear down everything — chat, engine, init state. Call from app
  /// lifecycle teardown (e.g. `_AppShellState.dispose` and the `detached`
  /// branch of `WidgetsBindingObserver.didChangeAppLifecycleState`).
  Future<void> shutdown() async {
    final pending = _pendingGeneration;
    if (pending != null) {
      try {
        await pending.future;
      } catch (_) {/* ignore */}
    }
    try {
      await _chat?.dispose();
    } catch (_) {/* ignore */}
    _chat = null;
    try {
      await _engine?.dispose();
    } catch (_) {/* ignore */}
    _engine = null;
    _ollamaMessages.clear();
    _initFuture = null;
    _sessionFuture = null;
    _modelReady = false;
  }

  String? _systemPromptTemplate;

  Future<String> _loadSystemPromptTemplate() async {
    _systemPromptTemplate ??=
        await rootBundle.loadString('assets/system_prompt.txt');
    return _systemPromptTemplate!;
  }

  void _trimHistory() {
    final maxBodyMessages = _maxHistoryPairs * 2;
    final bodyCount = _ollamaMessages.length - 1;
    if (bodyCount <= maxBodyMessages) return;
    final dropCount = bodyCount - maxBodyMessages;
    _ollamaMessages.removeRange(1, 1 + dropCount);
  }

  Future<String> _ollamaSendMessage(String userMessage) async {
    if (_ollamaMessages.isEmpty) {
      throw StateError('No active session. Call createSession first.');
    }
    final userTurn = {'role': 'user', 'content': userMessage};
    _ollamaMessages.add(userTurn);
    _trimHistory();

    final uri = Uri.parse('$_ollamaBaseUrl/chat/completions');
    final body = jsonEncode({
      'model': _ollamaModel,
      'messages': _ollamaMessages,
      'temperature': 0.4,
      'stream': false,
      'think': false,
    });

    debugPrint('[GemmaService] POST $uri model=$_ollamaModel '
        'turns=${_ollamaMessages.length}');

    try {
      final response = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (_ollamaApiKey != 'not-needed')
                'Authorization': 'Bearer $_ollamaApiKey',
            },
            body: body,
          )
          .timeout(const Duration(seconds: 90));

      if (response.statusCode != 200) {
        throw StateError(
            'Ollama returned ${response.statusCode}: ${response.body}');
      }

      final decoded = jsonDecode(utf8.decode(response.bodyBytes))
          as Map<String, dynamic>;
      final choices = decoded['choices'] as List<dynamic>?;
      if (choices == null || choices.isEmpty) {
        throw StateError('Ollama response had no choices: ${response.body}');
      }
      final content =
          ((choices.first as Map<String, dynamic>)['message']
                  as Map<String, dynamic>)['content'] as String? ??
              '';
      _ollamaMessages.add({'role': 'assistant', 'content': content});
      debugPrint('[GemmaService] ← ${content.length} chars');
      return content;
    } catch (e) {
      // Roll back the user turn so the next call doesn't send two
      // consecutive user messages (which OpenAI-compatible servers
      // either reject or treat as continuation).
      if (_ollamaMessages.isNotEmpty &&
          identical(_ollamaMessages.last, userTurn)) {
        _ollamaMessages.removeLast();
      }
      rethrow;
    }
  }
}
