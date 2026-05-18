import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'l10n/generated/app_localizations.dart';
import 'theme.dart';
import 'models/facility.dart';
import 'models/step.dart';
import 'models/guide_message.dart';
import 'models/topology.dart';
import 'services/facility_service.dart';
import 'services/gemma_service.dart';
import 'services/location_service.dart';
import 'services/query_orchestrator.dart';
import 'services/response_parser.dart';
import 'services/route_steps.dart';
import 'services/speech_service.dart';
import 'services/wayfinding_tools.dart';
import 'services/photo_location_service.dart';
import 'screens/home_screen.dart';
import 'screens/loading_screen.dart';
import 'screens/guide_screen.dart';
import 'screens/splash_screen.dart';
import 'widgets/origin_picker_sheet.dart';

AppLocalizations _l10n(BuildContext context) => AppLocalizations.of(context)!;

enum AppScreen { home, loading, guide }

class HealthWayfinderApp extends StatelessWidget {
  const HealthWayfinderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Medical Wayfinder',
      theme: appThemeLight(),
      darkTheme: appThemeDark(),
      themeMode: ThemeMode.system,
      debugShowCheckedModeBanner: false,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('en'),
        Locale('es'),
      ],
      home: const AppShell(),
    );
  }
}

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  AppScreen _screen = AppScreen.home;
  // Default to a placeholder until discoverFacilities() resolves and we swap
  // in the first real facility. Avoids a null-facility startup gap.
  Facility _facility = const Facility(id: '', name: 'Loading…', address: '', type: '');
  List<Facility> _facilities = const [];
  bool _bootstrapDone = false;
  Facility? _loadedFacility;
  QueryOrchestrator? _orchestrator;
  int _queryId = 0;

  // Guide conversation
  final List<GuideMessage> _guideMessages = [];

  // Most recent topology route from Resolved/ReOrientation. Empty when
  // the facility has no topology or the orchestrator returned no path.
  // _handleShowTheWay prefers this over re-parsing dept.directions.
  List<RouteStep> _currentRoute = const [];

  // Dedupe guard: iOS keyboards sometimes fire both onSubmitted AND the
  // send-button onTap for the same submission. Drop duplicates within
  // 750ms of an identical query.
  String? _lastQueryText;
  DateTime? _lastQueryAt;

  bool _isDuplicateSubmit(String text) {
    final now = DateTime.now();
    final last = _lastQueryAt;
    if (_lastQueryText == text &&
        last != null &&
        now.difference(last) < const Duration(milliseconds: 750)) {
      return true;
    }
    _lastQueryText = text;
    _lastQueryAt = now;
    return false;
  }

  // Accessibility preference
  bool _needsAccessibility = false;

  // Origin resolution: once-per-session GPS-or-picker handshake. Set true
  // after the first successful resolveOrigin OR after the user dismisses
  // the picker — we don't re-prompt mid-session. Reset on facility change
  // and _startOver. When the resulting origin is null (denied + skipped)
  // the orchestrator falls back to the default-parking-lot behavior.
  bool _originResolved = false;
  // Tracks whether origin resolution is currently in flight so the loading
  // copy can swap to "Locating you…" instead of the generic line.
  bool _locating = false;

  // Shared mic / STT state
  final _speech = SpeechService.instance;
  bool _isListening = false;
  String _partialText = '';
  bool _sttChecked = false;
  final _textFocusNode = FocusNode();

  // Pulse animation for loading state
  late AnimationController _breatheController;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _bootstrapFacilities();
    _breatheController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // `detached` fires just before the app process is killed. Tear down the
    // LlamaEngine + chat so the ~3.2 GB mmap and Metal context are released
    // cleanly. (On normal backgrounding iOS keeps the process alive and the
    // model in memory — we explicitly skip those transitions.)
    if (state == AppLifecycleState.detached) {
      // Fire-and-forget: the dispose() below will also fire.
      GemmaService.instance.shutdown();
    }
  }

  Future<void> _bootstrapFacilities() async {
    final list = await FacilityService.instance.discoverFacilities();
    if (!mounted) return;
    if (list.isEmpty) {
      setState(() => _bootstrapDone = true);
      return;
    }
    setState(() {
      _facilities = list;
      _facility = list.first;
      _bootstrapDone = true;
    });
    _loadFacilityData();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _textFocusNode.dispose();
    _breatheController.dispose();
    // Unconditional stopListening — it's a no-op when not active and
    // prevents a stale onResult callback from setState'ing on a disposed
    // widget after a timeout-induced listen end.
    _speech.stopListening();
    // Fire-and-forget: native engine shutdown is async; we don't block
    // the framework's dispose chain.
    GemmaService.instance.shutdown();
    super.dispose();
  }

  // --- Facility loading ---

  Future<void> _loadFacilityData() async {
    final loaded = await FacilityService.instance.loadFacility(_facility.id);
    if (mounted) {
      setState(() {
        _loadedFacility = loaded;
        _orchestrator = QueryOrchestrator(
          tools: WayfindingTools(loaded),
        );
        _orchestrator!.state.needsAccessibility = _needsAccessibility;
      });
    }
    // Prime the model session once per facility so the static system
    // prompt is sent (and cached by the runtime) only once. Per-turn
    // state goes in the user message.
    try {
      await GemmaService.instance.init();
      await GemmaService.instance.createSession();
    } catch (e) {
      debugPrint('[app] gemma session prime failed: $e');
    }
  }

  void _goTo(AppScreen screen) {
    setState(() {
      _screen = screen;
      if (_isListening) {
        _speech.stopListening();
        _isListening = false;
        _partialText = '';
      }
    });
    if (screen == AppScreen.loading) {
      _breatheController.repeat(reverse: true);
    } else {
      _breatheController.stop();
      _breatheController.reset();
    }
  }

  void _handleFacilityChanged(Facility f) {
    ++_queryId; // Invalidate any pending delayed callbacks
    setState(() {
      _facility = f;
      _loadedFacility = null;
      _orchestrator = null;
      _guideMessages.clear();
      _currentRoute = const [];
      _originResolved = false;
    });
    _loadFacilityData();
  }

  // --- Query handling ---

  Future<void> _handleQuery(String query) async {
    if (_isDuplicateSubmit(query)) return;
    final thisQueryId = ++_queryId;

    // Add user message to conversation
    setState(() {
      _guideMessages.add(GuideMessage.userQuery(query));
    });
    _goTo(AppScreen.loading);

    // Per-session origin resolution. On the first query we either get a
    // GPS fix → nearest node, or fall back to the chip picker. Subsequent
    // queries skip this immediately.
    final firstOriginCall = !_originResolved;
    await _ensureOrigin(thisQueryId);
    if (!mounted || thisQueryId != _queryId) return;

    // Skip the cosmetic 500ms when origin resolution already cost real
    // time (GPS fix or picker); the user has already waited long enough.
    if (!firstOriginCall) {
      await Future.delayed(const Duration(milliseconds: 500));
      if (!mounted || thisQueryId != _queryId) return;
    }
    if (_orchestrator == null) return;

    final OrchestratorResult result;
    try {
      result = _orchestrator!.processQuery(query);
    } catch (e, st) {
      debugPrint('[app] orchestrator failed: $e\n$st');
      setState(() {
        _guideMessages.add(GuideMessage.guideText(
          AppLocalizations.of(context)?.errorTroubleResponding ??
              "Sorry, I'm having trouble responding right now.",
        ));
      });
      _goTo(AppScreen.guide);
      return;
    }

    setState(() {
      switch (result) {
        case Resolved(:final department, :final route):
          _currentRoute = route;
          _guideMessages.add(GuideMessage.destination(department));
        case Disambig(:final candidates):
          _currentRoute = const [];
          _guideMessages.add(GuideMessage.disambig(candidates));
        case ReOrientation(:final destination, :final route, :final currentLocation):
          _currentRoute = route;
          _appendReOrientationMessages(destination, currentLocation, route);
        case NeedsModel(:final query, :final contextBlock):
          _currentRoute = const [];
          _handleNeedsModel(query, contextBlock, thisQueryId);
      }
    });
    _goTo(AppScreen.guide);
  }

  /// First-query origin handshake. Tries GPS, falls back to the chip
  /// picker on permission denial / failure / no-geo-nodes. Sets
  /// [_originResolved] true regardless of outcome so we don't re-prompt
  /// the user mid-session. When the origin ends up null the orchestrator
  /// falls back to today's parking-lot heuristic.
  Future<void> _ensureOrigin(int queryId) async {
    if (_originResolved) return;
    final graph = (_loadedFacility ?? _facility).topology;
    if (graph == null) {
      _originResolved = true;
      return;
    }

    setState(() => _locating = true);
    final result = await LocationService.instance.resolveOrigin(graph);
    if (!mounted || queryId != _queryId) {
      if (mounted) setState(() => _locating = false);
      return;
    }

    TopologyNode? origin;
    if (result is LocationResolved) {
      origin = result.node;
      debugPrint('[app] gps → ${origin.label} '
          '(accuracy ${result.accuracyMeters.toStringAsFixed(0)}m)');
      setState(() => _locating = false);
    } else {
      debugPrint('[app] gps non-resolved ($result); showing picker');
      // Keep _locating=true so the loading screen behind the modal keeps
      // saying "Locating you…" instead of reverting to "Finding your
      // destination…", which would be misleading while the user is being
      // asked to declare where they're starting from.
      origin = await OriginPickerSheet.show(context, graph: graph);
      if (!mounted || queryId != _queryId) {
        if (mounted) setState(() => _locating = false);
        return;
      }
    }

    if (origin != null && _orchestrator != null) {
      // Set sessionOrigin (sticky across department changes), NOT
      // currentLocation (which is the ephemeral re-orientation anchor
      // and gets wiped whenever a new destination is resolved).
      _orchestrator!.state.sessionOrigin = origin;
    }
    setState(() {
      _originResolved = true;
      _locating = false;
    });
  }

  // --- Guide conversation actions ---

  void _handleShowTheWay(Department dept) {
    final l10n = AppLocalizations.of(context);
    final steps = _currentRoute.isNotEmpty
        ? routeToSteps(
            _currentRoute,
            needsAccessibility: _needsAccessibility,
            l10n: l10n,
          )
        : _generateSteps(dept);
    setState(() {
      _guideMessages.add(GuideMessage.guideText(
        _needsAccessibility
            ? (l10n?.guideShowWayAccessible ?? "Let's get you there! I'll make sure to use accessible routes. Swipe through each step.")
            : (l10n?.guideShowWay ?? "Let's get you there! Swipe through each step."),
      ));
      _guideMessages.add(GuideMessage.steps(
        steps,
        route: _currentRoute.isNotEmpty ? _currentRoute : null,
        // The lightweight Facility from discoverFacilities() never
        // populates topology — the full graph lives on _loadedFacility.
        // Without this fallback the StepCarousel mini-map silently
        // renders the abstract painter instead of OSM polylines.
        graph: (_loadedFacility ?? _facility).topology,
      ));
    });
  }

  void _handleDisambigSelect(Department dept) {
    List<RouteStep> route = const [];
    if (_orchestrator != null) {
      final result = _orchestrator!.selectFromDisambig(dept);
      if (result is Resolved) route = result.route;
    }
    setState(() {
      _currentRoute = route;
      _guideMessages.add(GuideMessage.userQuery(dept.name));
      _guideMessages.add(GuideMessage.destination(dept));
    });
  }

  Future<void> _handleGuideInput(String text) async {
    if (_isDuplicateSubmit(text)) return;
    final thisQueryId = ++_queryId;
    setState(() {
      // A new query supersedes anything still pending from a prior turn —
      // most often a too-eager STT submit followed by the real query a
      // moment later. Sweep any orphan "Thinking…" placeholders so they
      // don't pile up forever (the prior turn's _runModel will return
      // early on queryId mismatch and never clean them up itself).
      _guideMessages.removeWhere(_isThinkingPlaceholder);
      _guideMessages.add(GuideMessage.userQuery(text));
    });

    if (_orchestrator == null) return;

    final firstOriginCall = !_originResolved;
    await _ensureOrigin(thisQueryId);
    if (!mounted || thisQueryId != _queryId) return;

    final OrchestratorResult result;
    try {
      result = _orchestrator!.processQuery(text);
    } catch (e, st) {
      debugPrint('[app] orchestrator failed: $e\n$st');
      setState(() {
        _guideMessages.add(GuideMessage.guideText(
          AppLocalizations.of(context)?.errorTroubleResponding ??
              "Sorry, I'm having trouble responding right now.",
        ));
      });
      return;
    }
    if (!firstOriginCall) {
      await Future.delayed(const Duration(milliseconds: 500));
      if (!mounted || thisQueryId != _queryId) return;
    }
    setState(() {
      switch (result) {
        case Resolved(:final department, :final route):
          _currentRoute = route;
          _guideMessages.add(GuideMessage.destination(department));
        case Disambig(:final candidates):
          _currentRoute = const [];
          _guideMessages.add(GuideMessage.disambig(candidates));
        case ReOrientation(:final destination, :final route, :final currentLocation):
          _currentRoute = route;
          _appendReOrientationMessages(destination, currentLocation, route);
        case NeedsModel(:final query, :final contextBlock):
          _currentRoute = const [];
          _handleNeedsModel(query, contextBlock, thisQueryId);
      }
    });
  }

  /// Route a NeedsModel result to the LLM. Mock mode short-circuits to
  /// the hardcoded fallback; ollama/device mode sends the query through
  /// the model with the orchestrator's context block. The model handles
  /// everything the orchestrator couldn't ground deterministically:
  /// re-orientation prompts, scope enforcement, follow-ups, unknown
  /// queries. The model's job is tone + format on top of the
  /// orchestrator's retrieval — knowledge stays in code.
  void _handleNeedsModel(String query, String contextBlock, int queryId) {
    _guideMessages.add(GuideMessage.thinking(
      AppLocalizations.of(context)?.thinking ?? 'Thinking…',
    ));
    _runModel(query, contextBlock, queryId);
  }

  Future<void> _runModel(String query, String contextBlock, int queryId) async {
    try {
      await GemmaService.instance.init();
      debugPrint('[app] query: $query');
      debugPrint('[app] contextBlock: ${contextBlock.length} chars');
      final raw = await GemmaService.instance.sendMessage(
        query,
        contextBlock: contextBlock,
      );
      if (!mounted || queryId != _queryId) return;
      debugPrint('[app] raw model response:\n$raw');
      final parsed = ResponseParser.parse(
        raw,
        l10n: AppLocalizations.of(context),
        facility: _loadedFacility ?? _facility,
      );
      setState(() {
        _replaceThinkingPlaceholder(parsed);
      });
    } catch (e, st) {
      debugPrint('[app] model call failed: $e\n$st');
      if (!mounted || queryId != _queryId) return;
      setState(() {
        _replaceThinkingPlaceholder([
          GuideMessage.guideText(
            AppLocalizations.of(context)?.errorTroubleResponding ??
                "Sorry, I'm having trouble responding right now.",
          ),
        ]);
      });
    }
  }

  void _replaceThinkingPlaceholder(List<GuideMessage> replacement) {
    // Find the most recent "Thinking…" placeholder and remove it. We can't
    // assume it's at the end — a fresher turn may have appended its own
    // user bubble or placeholder while this response was in flight, and
    // sweeping all matches (instead of just the last) ensures we never
    // leak an animated bubble forever.
    _guideMessages.removeWhere(_isThinkingPlaceholder);
    _guideMessages.addAll(replacement);
  }

  static bool _isThinkingPlaceholder(GuideMessage m) =>
      m.type == GuideMessageType.guideText && m.isPlaceholder;

  void _appendReOrientationMessages(
    Department dept,
    TopologyNode currentLocation,
    List<RouteStep> route,
  ) {
    final l10n = mounted ? AppLocalizations.of(context) : null;
    _guideMessages.add(GuideMessage.guideText(
      "Got it — I see you're near ${currentLocation.label}. Here's the way to ${dept.name}.",
    ));
    _guideMessages.add(GuideMessage.steps(
      routeToSteps(
        route,
        needsAccessibility: _needsAccessibility,
        l10n: l10n,
      ),
      route: route,
      graph: (_loadedFacility ?? _facility).topology,
    ));
  }

  void _handlePhotoTap() async {
    final facilityData = await FacilityService.instance.getFacilityData(_facility.id);
    final result = await PhotoLocationService.instance.pickAndLocate(
      facilityDataJson: facilityData,
      useCamera: false, // Use gallery on simulator; camera on real device
    );

    if (result == null || !mounted) return;

    // If the photo had GPS, snap it onto the topology graph and set
    // sessionOrigin. Without this the user takes a photo, sees "you're
    // near Building 5", asks for directions, and the route silently
    // ignores the photo's GPS and originates from the default parking lot.
    final graph = (_loadedFacility ?? _facility).topology;
    if (result.hasGps && graph != null && _orchestrator != null) {
      final snap = LocationService.instance.snapToGraph(
        graph,
        result.photoLat!,
        result.photoLng!,
      );
      if (snap is LocationResolved) {
        _orchestrator!.state.sessionOrigin = snap.node;
        _originResolved = true;
        debugPrint('[app] photo gps → ${snap.node.label}');
      } else {
        debugPrint('[app] photo gps non-resolved ($snap)');
      }
    }

    final response = PhotoLocationService.instance.buildLocationResponse(
      result,
      l10n: AppLocalizations.of(context),
    );
    setState(() {
      _guideMessages.add(GuideMessage.guideText(_l10n(context).photoCheckingLocation));
    });

    await Future.delayed(const Duration(seconds: 1));
    if (!mounted) return;

    setState(() {
      _guideMessages.add(GuideMessage.guideText(response));
    });
  }

  void _startOver() {
    _orchestrator?.state.reset();
    setState(() {
      _guideMessages.clear();
      _currentRoute = const [];
      _originResolved = false;
    });
    // Clear the model transcript so the next conversation starts fresh.
    // Re-prime the static system prompt — same content as before, so the
    // runtime prefix cache still hits.
    GemmaService.instance.createSession();
    _goTo(AppScreen.home);
  }

  // --- STT / mic ---

  void _toggleListening() async {
    if (!_sttChecked) {
      await _speech.initStt();
      _sttChecked = true;
    }

    if (!_speech.sttAvailable) {
      _textFocusNode.requestFocus();
      return;
    }

    if (_isListening) {
      await _speech.stopListening();
      if (!mounted) return;
      setState(() => _isListening = false);
      if (_partialText.isNotEmpty) {
        if (_screen == AppScreen.guide) {
          _handleGuideInput(_partialText);
        } else {
          _handleQuery(_partialText);
        }
      }
    } else {
      setState(() {
        _isListening = true;
        _partialText = '';
      });
      await _speech.startListening(
        onResult: (text, isFinal) {
          if (!mounted) return;
          setState(() => _partialText = text);
          if (isFinal && text.isNotEmpty) {
            // Re-check mounted before the second setState — async-gap
            // between setState calls is short but real.
            if (!mounted) return;
            setState(() => _isListening = false);
            if (_screen == AppScreen.guide) {
              _handleGuideInput(text);
            } else {
              _handleQuery(text);
            }
          }
        },
      );
    }
  }

  /// Build a step carousel for [dept]. We always prefer landmark-rich text
  /// over generic stubs: hand-authored `dept.directions` first, then a
  /// composed prose fallback that pulls in real facility data so the steps
  /// read like a person giving directions, not a template.
  List<WalkingStep> _generateSteps(Department dept) {
    if (dept.directions != null && dept.directions!.trim().isNotEmpty) {
      return _parseDirectionsToSteps(dept);
    }

    final l10n = mounted ? AppLocalizations.of(context) : null;
    final facility = _loadedFacility;

    // Compose a single prose paragraph from the facts we know, then split
    // it into landmark-shaped sentences. This avoids the generic 5-stub
    // template ("Exit parking toward campus" → "Building X is ahead" →
    // "Enter through main doors"), which loses every landmark detail and
    // even rendered placeholders like "Go to N/A" when fields were empty.
    final pieces = <String>[];

    final originHint = _composeOriginHint(dept, facility);
    if (originHint != null) pieces.add(originHint);

    pieces.add(_composeArrivalHint(dept, facility));

    final floorHint = _composeFloorHint(dept);
    if (floorHint != null) pieces.add(floorHint);

    final checkInText = (dept.checkIn != null && dept.checkIn!.trim().isNotEmpty)
        ? dept.checkIn!.trim()
        : (l10n?.stepCheckInDefault ?? 'Check in at the reception desk on arrival.');
    pieces.add(checkInText);

    final steps = <WalkingStep>[];
    for (var i = 0; i < pieces.length; i++) {
      final isLast = i == pieces.length - 1;
      String? badge;
      if (_needsAccessibility) {
        final lower = pieces[i].toLowerCase();
        if (lower.contains('elevator') ||
            (lower.contains('automatic') && lower.contains('door')) ||
            lower.contains('ramp') ||
            lower.contains('accessible')) {
          badge = l10n?.accessible ?? 'Accessible';
        }
      }
      if (i == 1 && dept.accessible) {
        badge ??= l10n?.wheelchairAccessible ?? 'Wheelchair accessible';
      }
      if (isLast) {
        badge = l10n?.youveArrived ?? "You've arrived";
      }
      steps.add(WalkingStep(
        number: i + 1,
        text: pieces[i],
        accessibilityBadge: badge,
      ));
    }
    return steps;
  }

  /// "From [parking name] ..." when we know which lot serves this dept,
  /// or null when we don't — so we don't fabricate a "head toward campus"
  /// instruction that has no anchor.
  String? _composeOriginHint(Department dept, Facility? facility) {
    if (facility == null || facility.parking.isEmpty) return null;
    ParkingArea? matching;
    for (final p in facility.parking) {
      if (p.nearestBuildings.contains(dept.building)) {
        matching = p;
        break;
      }
    }
    matching ??= facility.parking.first;
    final note = matching.entranceNote.trim();
    if (note.isNotEmpty) {
      // Use the authored entrance note verbatim — it already reads like
      // walking directions ("about a 2-minute walk south on Brookline...").
      return note;
    }
    return 'From ${matching.name}, walk toward the ${dept.building} entrance.';
  }

  /// "[Building name] at [address] — look for ..." style. Falls back to
  /// just the building name when we don't have richer facts.
  String _composeArrivalHint(Department dept, Facility? facility) {
    final building = dept.building.trim();
    if (facility == null) {
      return building.isEmpty
          ? 'Walk toward the main entrance.'
          : 'Walk to $building and go in through the main entrance.';
    }
    final addrParts = facility.address.split(',').map((s) => s.trim()).toList();
    final street = addrParts.isNotEmpty ? addrParts.first : '';
    final isSameAsFacility =
        building.isEmpty || building.toLowerCase() == facility.name.toLowerCase();
    final target = isSameAsFacility ? facility.name : building;
    if (street.isNotEmpty && isSameAsFacility) {
      return 'Look for $target at $street and walk in through the main entrance.';
    }
    return 'Walk to $target and go in through the main entrance.';
  }

  /// Floor cue that skips empty / placeholder values ("", "N/A", "TBD").
  String? _composeFloorHint(Department dept) {
    final l10n = mounted ? AppLocalizations.of(context) : null;
    final floorTrim = dept.floor.trim();
    final floorLower = floorTrim.toLowerCase();
    final isPlaceholder = floorTrim.isEmpty ||
        floorLower == 'n/a' ||
        floorLower == 'na' ||
        floorLower == 'none' ||
        floorLower == 'unknown' ||
        floorLower == '-' ||
        floorLower == 'tbd';
    final isGroundFloor = floorLower.contains('ground') ||
        floorLower.contains('1st') ||
        floorLower == '1';
    if (isPlaceholder || isGroundFloor) return null;
    return _needsAccessibility
        ? (l10n?.stepElevatorTo(floorTrim) ??
            'Take the elevator to $floorTrim.')
        : (l10n?.stepGoToFloor(floorTrim) ?? 'Take the elevator to $floorTrim.');
  }

  /// Parse the landmark-based directions string into individual steps
  List<WalkingStep> _parseDirectionsToSteps(Department dept) {
    final l10n = mounted ? AppLocalizations.of(context) : null;
    final sentences = dept.directions!
        .split('. ')
        .map((s) => s.trim().replaceAll(RegExp(r'\.$'), ''))
        .where((s) => s.isNotEmpty)
        .toList();

    final steps = <WalkingStep>[];
    for (var i = 0; i < sentences.length; i++) {
      final sentence = sentences[i];
      // Detect accessibility info in the sentence
      String? badge;
      if (_needsAccessibility) {
        if (sentence.toLowerCase().contains('accessible') ||
            sentence.toLowerCase().contains('automatic doors') ||
            sentence.toLowerCase().contains('elevator') ||
            sentence.toLowerCase().contains('ramp')) {
          badge = l10n?.accessible ?? 'Accessible';
        }
      }

      // Last step gets arrival badge
      final isLast = i == sentences.length - 1;

      steps.add(WalkingStep(
        number: i + 1,
        text: sentence,
        accessibilityBadge: isLast ? (l10n?.youveArrived ?? "You've arrived") : badge,
      ));
    }

    return steps;
  }

  // --- Mic layout ---

  ({double bottom, double size}) _micLayout(BuildContext context) {
    final bottomPadding = MediaQuery.of(context).padding.bottom;
    switch (_screen) {
      case AppScreen.home:
        return (bottom: 120 + bottomPadding, size: 80);
      case AppScreen.loading:
        return (bottom: 120 + bottomPadding, size: 80);
      case AppScreen.guide:
        return (bottom: 80 + bottomPadding, size: 64);
    }
  }

  @override
  Widget build(BuildContext context) {
    final micLayout = _micLayout(context);
    // Hide the floating mic overlay while the keyboard is up — otherwise it
    // collides with the home-screen accessibility chip and text input.
    final keyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0;
    // Also hide it during the splash bridge so the launch-screen handoff
    // doesn't pop a mic button onto a still-loading view.
    final hideMic = keyboardVisible || !_bootstrapDone;

    return Scaffold(
      // Tap-to-dismiss keyboard. The text field still focuses on tap because
      // GestureDetector with HitTestBehavior.translucent doesn't swallow
      // child taps.
      body: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTap: () => FocusScope.of(context).unfocus(),
        child: Stack(
        children: [
          // Screen content
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 350),
            switchInCurve: Curves.easeOut,
            switchOutCurve: Curves.easeIn,
            transitionBuilder: (child, animation) {
              final childKey = (child.key as ValueKey?)?.value?.toString() ?? '';
              final isIncoming = childKey.startsWith(_screen.name);

              return FadeTransition(
                opacity: animation,
                child: ScaleTransition(
                  scale: Tween<double>(
                    begin: isIncoming ? 0.95 : 1.05,
                    end: 1.0,
                  ).animate(CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOut,
                  )),
                  child: child,
                ),
              );
            },
            child: _buildScreen(),
          ),

          // Floating mic button overlay — hidden while keyboard is up so
          // it doesn't overlap the home-screen chip + input.
          AnimatedPositioned(
            duration: const Duration(milliseconds: 400),
            curve: Curves.easeInOut,
            bottom: micLayout.bottom,
            left: 0,
            right: 0,
            child: AnimatedOpacity(
              duration: const Duration(milliseconds: 200),
              opacity: hideMic ? 0.0 : 1.0,
              child: IgnorePointer(
                ignoring: hideMic,
                child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Partial text preview — wrapped in a card so it has
                  // its own backdrop and doesn't composite on top of any
                  // chat bubbles behind it.
                  if (_isListening && _partialText.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(24, 0, 24, 12),
                      child: ConstrainedBox(
                        constraints: BoxConstraints(
                          maxWidth: MediaQuery.of(context).size.width - 48,
                        ),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 10),
                          decoration: BoxDecoration(
                            color: context.surfaceColor,
                            borderRadius: BorderRadius.circular(20),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.08),
                                blurRadius: 12,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: Text(
                            _partialText,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 16,
                              color: context.textSecondary,
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                        ),
                      ),
                    ),
                  // The mic button
                  _FloatingMic(
                    size: micLayout.size,
                    isListening: _isListening,
                    isLoading: _screen == AppScreen.loading,
                    breatheAnimation: _breatheController,
                    onPressed: _screen == AppScreen.loading
                        ? null
                        : _toggleListening,
                  ),
                  const SizedBox(height: 10),
                  // Subtitle
                  if (_screen != AppScreen.loading)
                    Text(
                      _isListening
                          ? _l10n(context).listening
                          : _screen == AppScreen.home
                              ? _l10n(context).homeSubtitle
                              : _l10n(context).guideSubtitle,
                      style: TextStyle(fontSize: 14, color: context.textMuted),
                    ),
                ],
              ),
            ),
              ),
            ),
          ),
        ],
        ),
      ),
    );
  }

  Widget _buildScreen() {
    switch (_screen) {
      case AppScreen.home:
        // Bridge the iOS launch storyboard. While facility discovery is
        // still resolving, render the same visual composition as the
        // native launch screen so the handoff from iOS → Flutter looks
        // continuous instead of flashing a half-populated home screen.
        if (!_bootstrapDone) {
          return const SplashScreen(key: ValueKey('home_splash'));
        }
        return HomeScreen(
          key: ValueKey(AppScreen.home.name),
          facility: _facility,
          facilities: _facilities,
          bootstrapFailed: _bootstrapDone && _facilities.isEmpty,
          onFacilityChanged: _handleFacilityChanged,
          onQuery: _handleQuery,
          textFocusNode: _textFocusNode,
          needsAccessibility: _needsAccessibility,
          onAccessibilityChanged: (v) => setState(() {
            _needsAccessibility = v;
            if (_orchestrator != null) {
              _orchestrator!.state.needsAccessibility = v;
            }
          }),
        );

      case AppScreen.loading:
        return LoadingScreen(
          key: ValueKey(AppScreen.loading.name),
          facility: _facility,
          query: _guideMessages.isNotEmpty
              ? _guideMessages.last.text ?? ''
              : '',
          locating: _locating,
        );

      case AppScreen.guide:
        return GuideScreen(
          key: const ValueKey('guide'),
          facility: _facility,
          messages: _guideMessages,
          onShowTheWay: _handleShowTheWay,
          onDisambigSelect: _handleDisambigSelect,
          onSendMessage: _handleGuideInput,
          onStartOver: _startOver,
          onPhotoTap: _handlePhotoTap,
          textFocusNode: _textFocusNode,
        );
    }
  }
}

/// Floating mic button with pulse (listening) and breathe (loading) animations
class _FloatingMic extends StatefulWidget {
  final double size;
  final bool isListening;
  final bool isLoading;
  final Animation<double> breatheAnimation;
  final VoidCallback? onPressed;

  const _FloatingMic({
    required this.size,
    required this.isListening,
    required this.isLoading,
    required this.breatheAnimation,
    this.onPressed,
  });

  @override
  State<_FloatingMic> createState() => _FloatingMicState();
}

class _FloatingMicState extends State<_FloatingMic>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    if (widget.isListening) _pulseController.repeat();
  }

  @override
  void didUpdateWidget(_FloatingMic oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isListening && !oldWidget.isListening) {
      _pulseController.repeat();
    } else if (!widget.isListening && oldWidget.isListening) {
      _pulseController.stop();
      _pulseController.reset();
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final label = widget.isLoading
        ? (l10n?.a11yMicLoading ?? 'Loading, please wait')
        : widget.isListening
            ? (l10n?.a11yMicStop ?? 'Stop voice input')
            : (l10n?.a11yMicStart ?? 'Start voice input');
    return Semantics(
      button: true,
      enabled: !widget.isLoading,
      label: label,
      child: GestureDetector(
        onTap: widget.onPressed,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeInOut,
          width: widget.size + 20,
          height: widget.size + 20,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Pulse ring (listening)
            if (widget.isListening)
              AnimatedBuilder(
                animation: _pulseController,
                builder: (_, _) {
                  return Container(
                    width: widget.size + (20 * _pulseController.value),
                    height: widget.size + (20 * _pulseController.value),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: AppColors.teal.withValues(
                          alpha: 0.4 * (1 - _pulseController.value),
                        ),
                        width: 3,
                      ),
                    ),
                  );
                },
              ),
            // Breathe ring (loading)
            if (widget.isLoading && !widget.isListening)
              AnimatedBuilder(
                animation: widget.breatheAnimation,
                builder: (_, _) {
                  return Container(
                    width: widget.size + (8 * widget.breatheAnimation.value),
                    height: widget.size + (8 * widget.breatheAnimation.value),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: AppColors.teal.withValues(alpha: 0.15),
                        width: 2,
                      ),
                    ),
                  );
                },
              ),
            // The button
            AnimatedContainer(
              duration: const Duration(milliseconds: 400),
              curve: Curves.easeInOut,
              width: widget.size,
              height: widget.size,
              decoration: BoxDecoration(
                color: widget.isListening
                    ? Colors.red
                    : widget.isLoading
                        ? AppColors.teal.withValues(alpha: 0.7)
                        : AppColors.teal,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: (widget.isListening ? Colors.red : AppColors.teal)
                        .withValues(alpha: 0.3),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(
                widget.isListening ? Icons.stop : Icons.mic,
                size: widget.size * 0.375,
                color: Colors.white,
              ),
            ),
          ],
        ),
        ),
      ),
    );
  }
}
