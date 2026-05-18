import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_es.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('es'),
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Medical Wayfinder'**
  String get appTitle;

  /// No description provided for @homeTitle.
  ///
  /// In en, this message translates to:
  /// **'Where do you\nneed to go?'**
  String get homeTitle;

  /// No description provided for @homeSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Tap and tell me'**
  String get homeSubtitle;

  /// No description provided for @homeTextPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Or type here...'**
  String get homeTextPlaceholder;

  /// No description provided for @facilityPickerTitle.
  ///
  /// In en, this message translates to:
  /// **'Choose a facility'**
  String get facilityPickerTitle;

  /// No description provided for @facilityPickerSearch.
  ///
  /// In en, this message translates to:
  /// **'Search hospitals, clinics...'**
  String get facilityPickerSearch;

  /// No description provided for @facilityPickerNearby.
  ///
  /// In en, this message translates to:
  /// **'Nearby'**
  String get facilityPickerNearby;

  /// No description provided for @facilityPickerRecent.
  ///
  /// In en, this message translates to:
  /// **'Recent'**
  String get facilityPickerRecent;

  /// No description provided for @destinationLabel.
  ///
  /// In en, this message translates to:
  /// **'YOUR DESTINATION'**
  String get destinationLabel;

  /// No description provided for @showMeTheWay.
  ///
  /// In en, this message translates to:
  /// **'Show me the way'**
  String get showMeTheWay;

  /// No description provided for @notRightJustAsk.
  ///
  /// In en, this message translates to:
  /// **'Not right? Just ask'**
  String get notRightJustAsk;

  /// No description provided for @orJustTellMeMore.
  ///
  /// In en, this message translates to:
  /// **'Or just tell me more'**
  String get orJustTellMeMore;

  /// No description provided for @findingDestination.
  ///
  /// In en, this message translates to:
  /// **'Finding your destination...'**
  String get findingDestination;

  /// No description provided for @locatingYou.
  ///
  /// In en, this message translates to:
  /// **'Locating you...'**
  String get locatingYou;

  /// No description provided for @originPickerTitle.
  ///
  /// In en, this message translates to:
  /// **'Where are you starting from?'**
  String get originPickerTitle;

  /// No description provided for @originPickerSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Pick the spot closest to you so we can guide you in.'**
  String get originPickerSubtitle;

  /// No description provided for @originPickerSkip.
  ///
  /// In en, this message translates to:
  /// **'Skip'**
  String get originPickerSkip;

  /// No description provided for @whichOne.
  ///
  /// In en, this message translates to:
  /// **'WHICH ONE?'**
  String get whichOne;

  /// No description provided for @disambigQuestion.
  ///
  /// In en, this message translates to:
  /// **'There are a few options. Which one do you need?'**
  String get disambigQuestion;

  /// No description provided for @disambigFallback.
  ///
  /// In en, this message translates to:
  /// **'Not sure? The front desk can help you figure it out.'**
  String get disambigFallback;

  /// No description provided for @stepLabel.
  ///
  /// In en, this message translates to:
  /// **'STEP {number}'**
  String stepLabel(int number);

  /// No description provided for @progressFormat.
  ///
  /// In en, this message translates to:
  /// **'{current} of {total}'**
  String progressFormat(int current, int total);

  /// No description provided for @lostTapAndTellMe.
  ///
  /// In en, this message translates to:
  /// **'Lost? Tap and tell me'**
  String get lostTapAndTellMe;

  /// No description provided for @listening.
  ///
  /// In en, this message translates to:
  /// **'Listening...'**
  String get listening;

  /// No description provided for @back.
  ///
  /// In en, this message translates to:
  /// **'Back'**
  String get back;

  /// No description provided for @nextStep.
  ///
  /// In en, this message translates to:
  /// **'Next step'**
  String get nextStep;

  /// No description provided for @done.
  ///
  /// In en, this message translates to:
  /// **'Done'**
  String get done;

  /// No description provided for @backToSteps.
  ///
  /// In en, this message translates to:
  /// **'Back to steps'**
  String get backToSteps;

  /// No description provided for @youreHere.
  ///
  /// In en, this message translates to:
  /// **'You\'re here!'**
  String get youreHere;

  /// No description provided for @startNewSearch.
  ///
  /// In en, this message translates to:
  /// **'Start a new search'**
  String get startNewSearch;

  /// No description provided for @startOver.
  ///
  /// In en, this message translates to:
  /// **'Start over'**
  String get startOver;

  /// No description provided for @helpTitle.
  ///
  /// In en, this message translates to:
  /// **'Let\'s get you back on track'**
  String get helpTitle;

  /// No description provided for @helpInputPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Tell me what you see...'**
  String get helpInputPlaceholder;

  /// No description provided for @guideInputPlaceholder.
  ///
  /// In en, this message translates to:
  /// **'Type here...'**
  String get guideInputPlaceholder;

  /// No description provided for @guideSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Tap to talk to your guide'**
  String get guideSubtitle;

  /// No description provided for @guideShowWay.
  ///
  /// In en, this message translates to:
  /// **'Let\'s get you there! Swipe through each step.'**
  String get guideShowWay;

  /// No description provided for @guideShowWayAccessible.
  ///
  /// In en, this message translates to:
  /// **'Let\'s get you there! I\'ll make sure to use accessible routes. Swipe through each step.'**
  String get guideShowWayAccessible;

  /// No description provided for @accessible.
  ///
  /// In en, this message translates to:
  /// **'Accessible'**
  String get accessible;

  /// No description provided for @wheelchairAccessible.
  ///
  /// In en, this message translates to:
  /// **'Wheelchair accessible'**
  String get wheelchairAccessible;

  /// No description provided for @youveArrived.
  ///
  /// In en, this message translates to:
  /// **'You\'ve arrived'**
  String get youveArrived;

  /// No description provided for @accessibilityToggle.
  ///
  /// In en, this message translates to:
  /// **'I need accessible routes'**
  String get accessibilityToggle;

  /// No description provided for @distanceMi.
  ///
  /// In en, this message translates to:
  /// **'{distance} mi'**
  String distanceMi(double distance);

  /// No description provided for @photoCheckingLocation.
  ///
  /// In en, this message translates to:
  /// **'Checking your location from photo...'**
  String get photoCheckingLocation;

  /// No description provided for @stepExitParking.
  ///
  /// In en, this message translates to:
  /// **'Exit parking toward campus'**
  String get stepExitParking;

  /// No description provided for @stepBuildingAhead.
  ///
  /// In en, this message translates to:
  /// **'{building} is ahead'**
  String stepBuildingAhead(String building);

  /// No description provided for @stepEnterAccessible.
  ///
  /// In en, this message translates to:
  /// **'Enter through accessible entrance (automatic doors)'**
  String get stepEnterAccessible;

  /// No description provided for @stepEnterMain.
  ///
  /// In en, this message translates to:
  /// **'Enter through main doors'**
  String get stepEnterMain;

  /// No description provided for @stepElevatorTo.
  ///
  /// In en, this message translates to:
  /// **'Take the elevator to {floor}'**
  String stepElevatorTo(String floor);

  /// No description provided for @stepGoToFloor.
  ///
  /// In en, this message translates to:
  /// **'Go to {floor}'**
  String stepGoToFloor(String floor);

  /// No description provided for @stepCheckInDefault.
  ///
  /// In en, this message translates to:
  /// **'Check in at the front desk'**
  String get stepCheckInDefault;

  /// No description provided for @destinationFound.
  ///
  /// In en, this message translates to:
  /// **'I found {name} in {building}, {floor}.'**
  String destinationFound(String name, String building, String floor);

  /// No description provided for @destinationFoundNoFloor.
  ///
  /// In en, this message translates to:
  /// **'I found {name} in {building}.'**
  String destinationFoundNoFloor(String name, String building);

  /// No description provided for @noFacilitiesTitle.
  ///
  /// In en, this message translates to:
  /// **'No facilities available'**
  String get noFacilitiesTitle;

  /// No description provided for @noFacilitiesBody.
  ///
  /// In en, this message translates to:
  /// **'We couldn\'t load any facilities. Please reinstall the app or contact support.'**
  String get noFacilitiesBody;

  /// No description provided for @errorTroubleResponding.
  ///
  /// In en, this message translates to:
  /// **'Sorry, I\'m having trouble responding right now.'**
  String get errorTroubleResponding;

  /// No description provided for @thinking.
  ///
  /// In en, this message translates to:
  /// **'Thinking…'**
  String get thinking;

  /// No description provided for @badgeElevator.
  ///
  /// In en, this message translates to:
  /// **'Elevator'**
  String get badgeElevator;

  /// No description provided for @badgeRamp.
  ///
  /// In en, this message translates to:
  /// **'Ramp'**
  String get badgeRamp;

  /// No description provided for @badgeAutomaticDoors.
  ///
  /// In en, this message translates to:
  /// **'Automatic doors'**
  String get badgeAutomaticDoors;

  /// No description provided for @badgeAccessibleEntrance.
  ///
  /// In en, this message translates to:
  /// **'Accessible entrance'**
  String get badgeAccessibleEntrance;

  /// No description provided for @photoAtBuilding.
  ///
  /// In en, this message translates to:
  /// **'Based on your photo\'s location, you\'re right at {building}! Look for the entrance nearby.'**
  String photoAtBuilding(String building);

  /// No description provided for @photoNearBuilding.
  ///
  /// In en, this message translates to:
  /// **'Based on your photo\'s location, you\'re about {meters} meters from {building}. You\'re close — keep heading toward it.'**
  String photoNearBuilding(int meters, String building);

  /// No description provided for @photoHeadTowardBuilding.
  ///
  /// In en, this message translates to:
  /// **'Based on your photo\'s location, you\'re about {meters} meters from {building}. Head in that direction.'**
  String photoHeadTowardBuilding(int meters, String building);

  /// No description provided for @photoNoLocationData.
  ///
  /// In en, this message translates to:
  /// **'I couldn\'t find location data in that photo. Try taking a photo with your camera — it will include GPS coordinates that help me find where you are.'**
  String get photoNoLocationData;

  /// No description provided for @photoLocationTrouble.
  ///
  /// In en, this message translates to:
  /// **'I\'m having trouble determining your location from that photo.'**
  String get photoLocationTrouble;

  /// No description provided for @a11yMicStart.
  ///
  /// In en, this message translates to:
  /// **'Start voice input'**
  String get a11yMicStart;

  /// No description provided for @a11yMicStop.
  ///
  /// In en, this message translates to:
  /// **'Stop voice input'**
  String get a11yMicStop;

  /// No description provided for @a11yMicLoading.
  ///
  /// In en, this message translates to:
  /// **'Loading, please wait'**
  String get a11yMicLoading;

  /// No description provided for @a11ySendQuery.
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get a11ySendQuery;

  /// No description provided for @a11yChangeFacility.
  ///
  /// In en, this message translates to:
  /// **'Change facility'**
  String get a11yChangeFacility;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'es'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
