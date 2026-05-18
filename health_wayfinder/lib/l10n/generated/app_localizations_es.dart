// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get appTitle => 'Medical Wayfinder';

  @override
  String get homeTitle => '¿Adónde necesita\nir?';

  @override
  String get homeSubtitle => 'Toque y dígame';

  @override
  String get homeTextPlaceholder => 'O escriba aquí...';

  @override
  String get facilityPickerTitle => 'Elegir un centro';

  @override
  String get facilityPickerSearch => 'Buscar hospitales, clínicas...';

  @override
  String get facilityPickerNearby => 'Cercanos';

  @override
  String get facilityPickerRecent => 'Recientes';

  @override
  String get destinationLabel => 'SU DESTINO';

  @override
  String get showMeTheWay => 'Mostrar el camino';

  @override
  String get notRightJustAsk => '¿Incorrecto? Pregúnteme';

  @override
  String get orJustTellMeMore => 'O dígame más';

  @override
  String get findingDestination => 'Buscando su destino...';

  @override
  String get locatingYou => 'Ubicándolo...';

  @override
  String get originPickerTitle => '¿Desde dónde está empezando?';

  @override
  String get originPickerSubtitle =>
      'Elija el lugar más cercano para guiarlo desde ahí.';

  @override
  String get originPickerSkip => 'Omitir';

  @override
  String get whichOne => '¿CUÁL?';

  @override
  String get disambigQuestion => 'Hay varias opciones. ¿Cuál necesita?';

  @override
  String get disambigFallback =>
      '¿No está seguro? La recepción puede ayudarle.';

  @override
  String stepLabel(int number) {
    return 'PASO $number';
  }

  @override
  String progressFormat(int current, int total) {
    return '$current de $total';
  }

  @override
  String get lostTapAndTellMe => '¿Perdido? Toque y dígame';

  @override
  String get listening => 'Escuchando...';

  @override
  String get back => 'Atrás';

  @override
  String get nextStep => 'Siguiente';

  @override
  String get done => 'Listo';

  @override
  String get backToSteps => 'Volver a los pasos';

  @override
  String get youreHere => '¡Ya llegó!';

  @override
  String get startNewSearch => 'Nueva búsqueda';

  @override
  String get startOver => 'Empezar de nuevo';

  @override
  String get helpTitle => 'Vamos a encontrar el camino';

  @override
  String get helpInputPlaceholder => 'Dígame qué ve...';

  @override
  String get guideInputPlaceholder => 'Escriba aquí...';

  @override
  String get guideSubtitle => 'Toque para hablar con su guía';

  @override
  String get guideShowWay => '¡Vamos allá! Deslice por cada paso.';

  @override
  String get guideShowWayAccessible =>
      '¡Vamos allá! Me aseguraré de usar rutas accesibles. Deslice por cada paso.';

  @override
  String get accessible => 'Accesible';

  @override
  String get wheelchairAccessible => 'Accesible para sillas de ruedas';

  @override
  String get youveArrived => 'Ya llegó';

  @override
  String get accessibilityToggle => 'Necesito rutas accesibles';

  @override
  String distanceMi(double distance) {
    return '$distance mi';
  }

  @override
  String get photoCheckingLocation =>
      'Verificando su ubicación desde la foto...';

  @override
  String get stepExitParking => 'Salga del estacionamiento hacia el campus';

  @override
  String stepBuildingAhead(String building) {
    return '$building está adelante';
  }

  @override
  String get stepEnterAccessible =>
      'Entre por la entrada accesible (puertas automáticas)';

  @override
  String get stepEnterMain => 'Entre por la puerta principal';

  @override
  String stepElevatorTo(String floor) {
    return 'Tome el ascensor al $floor';
  }

  @override
  String stepGoToFloor(String floor) {
    return 'Vaya al $floor';
  }

  @override
  String get stepCheckInDefault => 'Regístrese en la recepción';

  @override
  String destinationFound(String name, String building, String floor) {
    return 'Encontré $name en $building, $floor.';
  }

  @override
  String destinationFoundNoFloor(String name, String building) {
    return 'Encontré $name en $building.';
  }

  @override
  String get noFacilitiesTitle => 'No hay centros disponibles';

  @override
  String get noFacilitiesBody =>
      'No pudimos cargar ningún centro. Reinstala la aplicación o contacta con soporte.';

  @override
  String get errorTroubleResponding =>
      'Lo siento, tengo problemas para responder en este momento.';

  @override
  String get thinking => 'Pensando…';

  @override
  String get badgeElevator => 'Ascensor';

  @override
  String get badgeRamp => 'Rampa';

  @override
  String get badgeAutomaticDoors => 'Puertas automáticas';

  @override
  String get badgeAccessibleEntrance => 'Entrada accesible';

  @override
  String photoAtBuilding(String building) {
    return 'Según la ubicación de la foto, ¡está justo en $building! Busque la entrada cercana.';
  }

  @override
  String photoNearBuilding(int meters, String building) {
    return 'Según la ubicación de la foto, está a unos $meters metros de $building. Está cerca — siga avanzando hacia allí.';
  }

  @override
  String photoHeadTowardBuilding(int meters, String building) {
    return 'Según la ubicación de la foto, está a unos $meters metros de $building. Diríjase en esa dirección.';
  }

  @override
  String get photoNoLocationData =>
      'No pude encontrar datos de ubicación en esa foto. Intente tomar una foto con su cámara — incluirá coordenadas GPS que me ayudarán a encontrar dónde está.';

  @override
  String get photoLocationTrouble =>
      'Tengo problemas para determinar su ubicación a partir de esa foto.';

  @override
  String get a11yMicStart => 'Iniciar entrada de voz';

  @override
  String get a11yMicStop => 'Detener entrada de voz';

  @override
  String get a11yMicLoading => 'Cargando, por favor espere';

  @override
  String get a11ySendQuery => 'Enviar';

  @override
  String get a11yChangeFacility => 'Cambiar de centro';
}
