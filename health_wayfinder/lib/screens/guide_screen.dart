import 'package:flutter/material.dart';
import '../l10n/generated/app_localizations.dart';
import '../theme.dart';
import '../models/facility.dart';
import '../models/guide_message.dart';
import '../services/speech_service.dart';
import '../widgets/user_bubble.dart';
import '../widgets/destination_card.dart';
import '../widgets/disambig_card.dart';
import '../widgets/step_carousel.dart';

class GuideScreen extends StatefulWidget {
  final Facility facility;
  final List<GuideMessage> messages;
  final void Function(Department dept) onShowTheWay;
  final void Function(Department dept) onDisambigSelect;
  final ValueChanged<String> onSendMessage;
  final VoidCallback onStartOver;
  final VoidCallback onPhotoTap;
  final FocusNode textFocusNode;

  const GuideScreen({
    super.key,
    required this.facility,
    required this.messages,
    required this.onShowTheWay,
    required this.onDisambigSelect,
    required this.onSendMessage,
    required this.onStartOver,
    required this.onPhotoTap,
    required this.textFocusNode,
  });

  @override
  State<GuideScreen> createState() => _GuideScreenState();
}

class _GuideScreenState extends State<GuideScreen> {
  final _scrollController = ScrollController();
  final _textController = TextEditingController();
  final _speech = SpeechService.instance;
  int _lastMessageCount = 0;

  @override
  void initState() {
    super.initState();
    _lastMessageCount = widget.messages.length;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _speakLatestGuideMessage();
    });
  }

  @override
  void didUpdateWidget(GuideScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.messages.length > _lastMessageCount) {
      _lastMessageCount = widget.messages.length;
      _scrollToBottom();
      _speakLatestGuideMessage();
    }
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _textController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _speakLatestGuideMessage() {
    if (!mounted) return;
    if (widget.messages.isEmpty) return;
    final last = widget.messages.last;
    // Don't speak the "Thinking…" placeholder — locale-independent.
    // (Comparing against the literal string broke in Spanish where the
    // bubble renders as "Pensando…".)
    if (last.isPlaceholder) return;
    final l10n = AppLocalizations.of(context);
    switch (last.type) {
      case GuideMessageType.guideText:
        final text = last.text ?? '';
        _speech.stopSpeaking();
        _speech.speakAsync(text);
        break;
      case GuideMessageType.destinationCard:
        final dept = last.department;
        if (dept != null) {
          _speech.stopSpeaking();
          final hasFloor = dept.floor.trim().isNotEmpty;
          final spoken = hasFloor
              ? (l10n?.destinationFound(dept.name, dept.building, dept.floor) ??
                  'I found ${dept.name} in ${dept.building}, ${dept.floor}.')
              : (l10n?.destinationFoundNoFloor(dept.name, dept.building) ??
                  'I found ${dept.name} in ${dept.building}.');
          _speech.speakAsync(spoken);
        }
        break;
      case GuideMessageType.arrival:
        _speech.stopSpeaking();
        _speech.speakAsync(l10n?.youveArrived ?? "You've arrived!");
        break;
      case GuideMessageType.disambigCard:
        _speech.stopSpeaking();
        _speech.speakAsync(l10n?.disambigQuestion ?? 'There are a few options. Which one do you need?');
        break;
      default:
        break;
    }
  }

  void _sendText() {
    final text = _textController.text.trim();
    if (text.isNotEmpty) {
      _textController.clear();
      widget.onSendMessage(text);
    }
  }

  @override
  Widget build(BuildContext context) {
    final topPadding = MediaQuery.of(context).padding.top;

    return Container(
      color: context.screenBg,
      child: Column(
        children: [
          // Header
          Container(
            color: context.surfaceColor,
            padding: EdgeInsets.fromLTRB(24, 14 + topPadding, 24, 14),
            child: Row(
              children: [
                GestureDetector(
                  onTap: widget.onStartOver,
                  child: Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: context.tealLightAdaptive,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.location_on,
                      size: 18,
                      color: AppColors.teal,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        widget.facility.name.toUpperCase(),
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                          color: context.textMuted,
                          letterSpacing: 1.4,
                          height: 1.1,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Wayfinder',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                          fontFamily: 'Georgia',
                          color: context.textPrimary,
                          height: 1.1,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                // Mute toggle
                GestureDetector(
                  onTap: () {
                    setState(() {
                      _speech.muted = !_speech.muted;
                    });
                    if (_speech.muted) _speech.stopSpeaking();
                  },
                  child: Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: _speech.muted
                          ? context.chipBg
                          : context.tealLightAdaptive,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      _speech.muted ? Icons.volume_off : Icons.volume_up,
                      size: 18,
                      color: _speech.muted
                          ? context.textMuted
                          : AppColors.teal,
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                GestureDetector(
                  onTap: widget.onStartOver,
                  child: Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: context.chipBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.restart_alt,
                      size: 18,
                      color: context.textMuted,
                    ),
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: context.borderColor),

          // Conversation thread
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 120),
              itemCount: widget.messages.length,
              itemBuilder: (context, index) {
                return _buildMessage(widget.messages[index]);
              },
            ),
          ),

          // Text input bar
          Container(
            padding: const EdgeInsets.fromLTRB(24, 12, 24, 40),
            decoration: BoxDecoration(
              color: context.surfaceColor,
              border: Border(top: BorderSide(color: context.borderColor)),
            ),
            child: Row(
              children: [
                GestureDetector(
                  onTap: widget.onPhotoTap,
                  child: Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: context.chipBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.camera_alt,
                      size: 20,
                      color: context.textMuted,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: _textController,
                    focusNode: widget.textFocusNode,
                    decoration: InputDecoration(
                      hintText: AppLocalizations.of(context)!.guideInputPlaceholder,
                      hintStyle: TextStyle(color: context.textMuted),
                      contentPadding:
                          const EdgeInsets.symmetric(horizontal: 18),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(999),
                        borderSide:
                            BorderSide(color: context.inputBorder, width: 1.5),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(999),
                        borderSide:
                            BorderSide(color: context.inputBorder, width: 1.5),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(999),
                        borderSide: const BorderSide(
                            color: AppColors.teal, width: 1.5),
                      ),
                    ),
                    onSubmitted: (_) => _sendText(),
                  ),
                ),
                const SizedBox(width: 10),
                Semantics(
                  button: true,
                  label: AppLocalizations.of(context)!.a11ySendQuery,
                  child: GestureDetector(
                    onTap: _sendText,
                    child: Container(
                      width: 48,
                      height: 48,
                      decoration: const BoxDecoration(
                        color: AppColors.teal,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.send, size: 20, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessage(GuideMessage message) {
    switch (message.type) {
      case GuideMessageType.userQuery:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: UserBubble(text: message.text ?? ''),
        );

      case GuideMessageType.destinationCard:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: DestinationCard(
            department: message.department!,
            onShowTheWay: () => widget.onShowTheWay(message.department!),
          ),
        );

      case GuideMessageType.disambigCard:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: DisambigCard(
            question: message.text?.trim().isNotEmpty == true
                ? message.text!
                : AppLocalizations.of(context)!.disambigQuestion,
            options: message.options!,
            onSelected: widget.onDisambigSelect,
          ),
        );

      case GuideMessageType.stepCarousel:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: StepCarousel(
            steps: message.steps!,
            route: message.route,
            graph: message.graph,
          ),
        );

      case GuideMessageType.guideText:
        return Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: _GuideBubble(
            text: message.text ?? '',
            isPlaceholder: message.isPlaceholder,
          ),
        );

      case GuideMessageType.arrival:
        // Arrival is handled by the last step's "You've arrived" badge
        return const SizedBox.shrink();
    }
  }
}

/// Left-aligned guide text bubble
class _GuideBubble extends StatelessWidget {
  final String text;
  final bool isPlaceholder;

  const _GuideBubble({required this.text, this.isPlaceholder = false});

  @override
  Widget build(BuildContext context) {
    // Use the message's `isPlaceholder` flag rather than comparing against
    // the localized "Thinking…" string, which broke in Spanish.
    final isThinking = isPlaceholder;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.85,
        ),
        padding: EdgeInsets.symmetric(
          horizontal: 14,
          vertical: isThinking ? 16 : 14,
        ),
        decoration: BoxDecoration(
          color: context.chipBg,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(16),
            bottomRight: Radius.circular(16),
          ),
          border: const Border(
            left: BorderSide(color: AppColors.teal, width: 3),
          ),
        ),
        child: isThinking
            ? const _TypingDots()
            : Text(
                text,
                style: TextStyle(
                  fontSize: 15,
                  color: context.textSecondary,
                  height: 1.5,
                ),
              ),
      ),
    );
  }
}

/// Three bouncing dots used as a "model is thinking" indicator.
class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 14,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: List.generate(3, (i) {
          return Padding(
            padding: EdgeInsets.only(right: i < 2 ? 6 : 0),
            child: AnimatedBuilder(
              animation: _controller,
              builder: (context, _) {
                // Each dot is offset by 1/3 of the cycle so the wave moves
                // left-to-right. sin curve gives a smooth up/down bounce.
                final phase = (_controller.value - i * 0.18) % 1.0;
                final t = (1 - (phase * 2 - 1).abs()).clamp(0.0, 1.0);
                final offsetY = -4.0 * t;
                final opacity = 0.4 + 0.6 * t;
                return Transform.translate(
                  offset: Offset(0, offsetY),
                  child: Opacity(
                    opacity: opacity,
                    child: Container(
                      width: 7,
                      height: 7,
                      decoration: const BoxDecoration(
                        color: AppColors.teal,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                );
              },
            ),
          );
        }),
      ),
    );
  }
}

