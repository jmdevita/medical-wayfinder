// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Medical Wayfinder';

  @override
  String get homeTitle => 'Where do you\nneed to go?';

  @override
  String get homeSubtitle => 'Tap and tell me';

  @override
  String get homeTextPlaceholder => 'Or type here...';

  @override
  String get facilityPickerTitle => 'Choose a facility';

  @override
  String get facilityPickerSearch => 'Search hospitals, clinics...';

  @override
  String get facilityPickerNearby => 'Nearby';

  @override
  String get facilityPickerRecent => 'Recent';

  @override
  String get destinationLabel => 'YOUR DESTINATION';

  @override
  String get showMeTheWay => 'Show me the way';

  @override
  String get notRightJustAsk => 'Not right? Just ask';

  @override
  String get orJustTellMeMore => 'Or just tell me more';

  @override
  String get findingDestination => 'Finding your destination...';

  @override
  String get locatingYou => 'Locating you...';

  @override
  String get originPickerTitle => 'Where are you starting from?';

  @override
  String get originPickerSubtitle =>
      'Pick the spot closest to you so we can guide you in.';

  @override
  String get originPickerSkip => 'Skip';

  @override
  String get whichOne => 'WHICH ONE?';

  @override
  String get disambigQuestion =>
      'There are a few options. Which one do you need?';

  @override
  String get disambigFallback =>
      'Not sure? The front desk can help you figure it out.';

  @override
  String stepLabel(int number) {
    return 'STEP $number';
  }

  @override
  String progressFormat(int current, int total) {
    return '$current of $total';
  }

  @override
  String get lostTapAndTellMe => 'Lost? Tap and tell me';

  @override
  String get listening => 'Listening...';

  @override
  String get back => 'Back';

  @override
  String get nextStep => 'Next step';

  @override
  String get done => 'Done';

  @override
  String get backToSteps => 'Back to steps';

  @override
  String get youreHere => 'You\'re here!';

  @override
  String get startNewSearch => 'Start a new search';

  @override
  String get startOver => 'Start over';

  @override
  String get helpTitle => 'Let\'s get you back on track';

  @override
  String get helpInputPlaceholder => 'Tell me what you see...';

  @override
  String get guideInputPlaceholder => 'Type here...';

  @override
  String get guideSubtitle => 'Tap to talk to your guide';

  @override
  String get guideShowWay => 'Let\'s get you there! Swipe through each step.';

  @override
  String get guideShowWayAccessible =>
      'Let\'s get you there! I\'ll make sure to use accessible routes. Swipe through each step.';

  @override
  String get accessible => 'Accessible';

  @override
  String get wheelchairAccessible => 'Wheelchair accessible';

  @override
  String get youveArrived => 'You\'ve arrived';

  @override
  String get accessibilityToggle => 'I need accessible routes';

  @override
  String distanceMi(double distance) {
    return '$distance mi';
  }

  @override
  String get photoCheckingLocation => 'Checking your location from photo...';

  @override
  String get stepExitParking => 'Exit parking toward campus';

  @override
  String stepBuildingAhead(String building) {
    return '$building is ahead';
  }

  @override
  String get stepEnterAccessible =>
      'Enter through accessible entrance (automatic doors)';

  @override
  String get stepEnterMain => 'Enter through main doors';

  @override
  String stepElevatorTo(String floor) {
    return 'Take the elevator to $floor';
  }

  @override
  String stepGoToFloor(String floor) {
    return 'Go to $floor';
  }

  @override
  String get stepCheckInDefault => 'Check in at the front desk';

  @override
  String destinationFound(String name, String building, String floor) {
    return 'I found $name in $building, $floor.';
  }

  @override
  String destinationFoundNoFloor(String name, String building) {
    return 'I found $name in $building.';
  }

  @override
  String get noFacilitiesTitle => 'No facilities available';

  @override
  String get noFacilitiesBody =>
      'We couldn\'t load any facilities. Please reinstall the app or contact support.';

  @override
  String get errorTroubleResponding =>
      'Sorry, I\'m having trouble responding right now.';

  @override
  String get thinking => 'Thinking…';

  @override
  String get badgeElevator => 'Elevator';

  @override
  String get badgeRamp => 'Ramp';

  @override
  String get badgeAutomaticDoors => 'Automatic doors';

  @override
  String get badgeAccessibleEntrance => 'Accessible entrance';

  @override
  String photoAtBuilding(String building) {
    return 'Based on your photo\'s location, you\'re right at $building! Look for the entrance nearby.';
  }

  @override
  String photoNearBuilding(int meters, String building) {
    return 'Based on your photo\'s location, you\'re about $meters meters from $building. You\'re close — keep heading toward it.';
  }

  @override
  String photoHeadTowardBuilding(int meters, String building) {
    return 'Based on your photo\'s location, you\'re about $meters meters from $building. Head in that direction.';
  }

  @override
  String get photoNoLocationData =>
      'I couldn\'t find location data in that photo. Try taking a photo with your camera — it will include GPS coordinates that help me find where you are.';

  @override
  String get photoLocationTrouble =>
      'I\'m having trouble determining your location from that photo.';

  @override
  String get a11yMicStart => 'Start voice input';

  @override
  String get a11yMicStop => 'Stop voice input';

  @override
  String get a11yMicLoading => 'Loading, please wait';

  @override
  String get a11ySendQuery => 'Send';

  @override
  String get a11yChangeFacility => 'Change facility';
}
