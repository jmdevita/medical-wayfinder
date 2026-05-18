import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:speech_to_text/speech_recognition_result.dart';

class SpeechService {
  static final SpeechService _instance = SpeechService._();
  static SpeechService get instance => _instance;
  SpeechService._();

  final FlutterTts _tts = FlutterTts();
  final SpeechToText _stt = SpeechToText();

  bool _ttsInitialized = false;
  bool _sttAvailable = false;
  bool _isListening = false;
  bool _isSpeaking = false;
  bool muted = false;

  bool get isListening => _isListening;
  bool get isSpeaking => _isSpeaking;
  bool get sttAvailable => _sttAvailable;

  bool _ttsAvailable = true;

  /// Initialize TTS engine. Picks the highest-quality voice the device has
  /// installed, falling back gracefully if the user only has compact voices.
  ///
  /// iOS exposes a `quality` field per voice:
  ///   2 = premium  (neural, ~200 MB download, Siri-class)
  ///   1 = enhanced (~100 MB download, much better than compact)
  ///   0 = default  (compact, preinstalled, the robotic-sounding ones)
  ///
  /// Premium and enhanced voices are FREE but the user must download them
  /// once via Settings → Accessibility → Spoken Content → Voices. We log
  /// what quality we ended up with so we can prompt the user later if
  /// they're stuck on default.
  Future<void> initTts() async {
    if (_ttsInitialized) return;

    try {
      // iOS audio routing: playback category + speaker default keeps the
      // voice audible even when the device is on silent and routes to the
      // built-in speaker rather than the earpiece (which sounds muffled
      // and is the default routing under some categories).
      await _tts.setIosAudioCategory(
        IosTextToSpeechAudioCategory.playback,
        [
          IosTextToSpeechAudioCategoryOptions.allowBluetooth,
          IosTextToSpeechAudioCategoryOptions.allowBluetoothA2DP,
          IosTextToSpeechAudioCategoryOptions.mixWithOthers,
          IosTextToSpeechAudioCategoryOptions.defaultToSpeaker,
        ],
        IosTextToSpeechAudioMode.spokenAudio,
      );
      await _tts.setLanguage('en-US');
      await _tts.setSpeechRate(0.5);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
      await _selectBestVoice();
      _ttsInitialized = true;
      debugPrint('[SpeechService] TTS initialized');
    } catch (e) {
      debugPrint('[SpeechService] TTS not available (simulator?): $e');
      _ttsAvailable = false;
      _ttsInitialized = true; // Don't retry
    }
  }

  /// Pick the best available voice by quality tier, then by gender bias.
  /// Sets [bestInstalledQuality] so callers can prompt the user to enable
  /// a better voice in Settings if needed.
  Future<void> _selectBestVoice({String localePrefix = 'en'}) async {
    final voices = await _tts.getVoices;
    if (voices is! List) return;

    // Normalize to a uniform shape. iOS gives us {name, locale, quality,
    // gender, identifier}. Android gives us {name, locale} (network voices
    // are picked automatically by the system for supported locales).
    int qualityRank(Map v) {
      final raw = v['quality'];
      // iOS returns int (0/1/2). Some plugin versions return strings.
      if (raw is int) return raw;
      if (raw is String) {
        final s = raw.toLowerCase();
        if (s == 'premium' || s == '2') return 2;
        if (s == 'enhanced' || s == '1') return 1;
        return 0;
      }
      // Heuristic for plugins that don't surface quality: identifier
      // contains "premium" / "enhanced" for downloaded voices.
      final id = (v['identifier'] ?? v['name'] ?? '').toString().toLowerCase();
      if (id.contains('premium')) return 2;
      if (id.contains('enhanced')) return 1;
      return 0;
    }

    final candidates = voices
        .cast<Map>()
        .where((v) {
          final loc = (v['locale'] as String?) ?? '';
          return loc.toLowerCase().startsWith(localePrefix.toLowerCase());
        })
        .toList()
      ..sort((a, b) {
        final byQuality = qualityRank(b).compareTo(qualityRank(a));
        if (byQuality != 0) return byQuality;
        // At equal quality, slight bias toward female voices — research
        // shows patients rate female voices as warmer in healthcare
        // contexts. Falls through if neither voice tags gender.
        final ag = (a['gender'] as String?)?.toLowerCase() ?? '';
        final bg = (b['gender'] as String?)?.toLowerCase() ?? '';
        if (ag == 'female' && bg != 'female') return -1;
        if (bg == 'female' && ag != 'female') return 1;
        return 0;
      });

    if (candidates.isEmpty) return;
    final pick = candidates.first;
    bestInstalledQuality = qualityRank(pick);

    // setVoice payload: identifier is most precise on iOS; fall back to
    // name+locale for Android and older iOS.
    final identifier = pick['identifier'] as String?;
    final name = pick['name'] as String?;
    final locale = pick['locale'] as String?;
    final payload = <String, String>{};
    if (identifier != null) payload['identifier'] = identifier;
    if (name != null) payload['name'] = name;
    if (locale != null) payload['locale'] = locale;
    if (payload.isEmpty) return;
    await _tts.setVoice(payload);
    debugPrint('[SpeechService] Selected voice: '
        'name=${pick['name']} quality=$bestInstalledQuality '
        'identifier=${pick['identifier']}');
    if (bestInstalledQuality < 2) {
      debugPrint(
          '[SpeechService] Tip: enable a premium voice via '
          'Settings → Accessibility → Spoken Content → Voices for '
          'dramatically better TTS quality.');
    }
  }

  /// 0 = default (compact, robotic), 1 = enhanced, 2 = premium (neural).
  /// Read by the UI so we can prompt the user to install a better voice.
  int bestInstalledQuality = 0;

  /// Initialize STT engine
  Future<bool> initStt() async {
    try {
      _sttAvailable = await _stt.initialize(
        onError: (error) {
          debugPrint('[SpeechService] STT error: ${error.errorMsg}');
          _isListening = false;
        },
        onStatus: (status) {
          debugPrint('[SpeechService] STT status: $status');
          if (status == 'done' || status == 'notListening') {
            _isListening = false;
          }
        },
      );
    } catch (e) {
      debugPrint('[SpeechService] STT not available (simulator?): $e');
      _sttAvailable = false;
    }
    debugPrint('[SpeechService] STT available: $_sttAvailable');
    return _sttAvailable;
  }

  /// Tracks the in-flight speak's completer. `flutter_tts` only supports
  /// a single completion handler globally — if a second speak starts
  /// before the first finishes, we complete the previous completer
  /// immediately so its awaiter doesn't hang forever.
  Completer<void>? _currentCompleter;

  /// Speak text aloud. Returns when speech completes.
  /// Respects mute setting.
  Future<void> speak(String text) async {
    if (muted || text.isEmpty) return;

    await initTts();
    if (!_ttsAvailable) return;

    // Force-complete any prior in-flight completer so its awaiter doesn't
    // get stranded when we replace the global completion handler.
    final prior = _currentCompleter;
    if (prior != null && !prior.isCompleted) prior.complete();

    _isSpeaking = true;
    final completer = Completer<void>();
    _currentCompleter = completer;
    _tts.setCompletionHandler(() {
      _isSpeaking = false;
      if (!completer.isCompleted) completer.complete();
    });

    try {
      await _tts.speak(text);
      await completer.future;
    } catch (e) {
      _isSpeaking = false;
      if (!completer.isCompleted) completer.complete();
      debugPrint('[SpeechService] speak failed: $e');
    }
  }

  /// Speak text without waiting for completion
  Future<void> speakAsync(String text) async {
    if (muted || text.isEmpty) return;

    await initTts();
    if (!_ttsAvailable) return;

    // Force-complete any prior speak() awaiter — see comment on _currentCompleter.
    final prior = _currentCompleter;
    if (prior != null && !prior.isCompleted) prior.complete();
    _currentCompleter = null;

    _isSpeaking = true;
    _tts.setCompletionHandler(() {
      _isSpeaking = false;
    });
    try {
      await _tts.speak(text);
    } catch (e) {
      _isSpeaking = false;
      debugPrint('[SpeechService] speakAsync failed: $e');
    }
  }

  /// Stop any current speech
  Future<void> stopSpeaking() async {
    _isSpeaking = false;
    if (!_ttsAvailable) return;
    try {
      await _tts.stop();
    } catch (e) {
      debugPrint('[SpeechService] stopSpeaking failed: $e');
    }
  }

  /// Start listening for speech input
  Future<void> startListening({
    required void Function(String text, bool isFinal) onResult,
    String locale = 'en-US',
  }) async {
    if (!_sttAvailable) {
      final available = await initStt();
      if (!available) {
        debugPrint('[SpeechService] STT not available on this device');
        return;
      }
    }

    // Stop TTS if speaking (don't listen to ourselves)
    if (_isSpeaking) await stopSpeaking();

    _isListening = true;
    await _stt.listen(
      onResult: (SpeechRecognitionResult result) {
        onResult(result.recognizedWords, result.finalResult);
        if (result.finalResult) {
          _isListening = false;
        }
      },
      localeId: locale,
      // Auto-stop tuned to voice-assistant norms (Siri / Google Assistant):
      // - pauseFor: stop ~2s after the patient stops speaking. Long enough
      //   to tolerate a mid-sentence pause, short enough that they don't
      //   wait forever for the model to start working.
      // - listenFor: hard backstop in case the mic gets stuck open.
      // - ListenMode.search is the plugin's "voice command" mode — more
      //   aggressive about end-of-speech detection than dictation mode.
      pauseFor: const Duration(seconds: 2),
      listenFor: const Duration(seconds: 30),
      listenOptions: SpeechListenOptions(
        listenMode: ListenMode.search,
        cancelOnError: true,
      ),
    );
  }

  /// Stop listening
  Future<void> stopListening() async {
    _isListening = false;
    await _stt.stop();
  }

  /// Set language for TTS
  Future<void> setLanguage(String locale) async {
    await initTts();
    if (!_ttsAvailable) return;
    try {
      await _tts.setLanguage(locale);
    } catch (e) {
      debugPrint('[SpeechService] setLanguage failed: $e');
    }
  }

  /// Build spoken text for a walking step
  String buildStepText({
    required int stepNumber,
    required String instruction,
    String? accessibilityBadge,
    bool isLastStep = false,
  }) {
    var text = 'Step $stepNumber: $instruction.';
    if (accessibilityBadge != null && !isLastStep) {
      text += ' $accessibilityBadge.';
    }
    return text;
  }
}
