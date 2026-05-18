import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../models/topology.dart';
import '../theme.dart';

/// Static mini-map shown on each step card. Renders building footprints +
/// footways from the baked OSM layer and the walking route on top, with the
/// active edge highlighted. Gestures are disabled — the carousel owns swipe.
///
/// Internally this widget caches the per-(graph, route) static layers
/// (polygons, footways, bounds, full-route polyline) so a PageView swipe
/// — which only changes `activeEdgeIndex` — doesn't reallocate ~100 OSM
/// polygons + iterate every feature point on every rebuild.
class RouteMiniMap extends StatefulWidget {
  final CampusGraph graph;
  final List<RouteStep> route;
  final int activeEdgeIndex;

  const RouteMiniMap({
    super.key,
    required this.graph,
    required this.route,
    required this.activeEdgeIndex,
  });

  @override
  State<RouteMiniMap> createState() => _RouteMiniMapState();
}

class _RouteMiniMapState extends State<RouteMiniMap> {
  List<LatLng> _routePoints = const [];
  LatLngBounds? _bounds;
  List<Polygon> _staticPolygons = const [];
  List<Polyline> _staticFootways = const [];
  List<Polyline> _fullRouteLine = const [];

  @override
  void initState() {
    super.initState();
    _rebuildStatic();
  }

  @override
  void didUpdateWidget(RouteMiniMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Rebuild the static caches only when graph or route identity changes.
    // PageView swipe only mutates activeEdgeIndex, which we use to compute
    // the active overlay in build() but doesn't invalidate the static stuff.
    final graphChanged = !identical(oldWidget.graph, widget.graph);
    final routeChanged = !identical(oldWidget.route, widget.route);
    if (graphChanged || routeChanged) {
      _rebuildStatic();
    }
  }

  void _rebuildStatic() {
    final routePoints = _computeRoutePoints(widget.route);
    _routePoints = routePoints;
    if (routePoints.length < 2) {
      _bounds = null;
      _staticPolygons = const [];
      _staticFootways = const [];
      _fullRouteLine = const [];
      return;
    }
    final boundsPoints = <LatLng>[
      ...routePoints,
      for (final f in widget.graph.osm.features)
        for (final p in f.polygon)
          if (p.length >= 2) LatLng(p[0], p[1]),
    ];
    _bounds = LatLngBounds.fromPoints(boundsPoints);
    _staticPolygons = [
      for (final f in widget.graph.osm.features)
        if (f.polygon.length >= 3)
          Polygon(
            points: [for (final p in f.polygon) LatLng(p[0], p[1])],
            color: f.isParking
                ? AppColors.paper.withValues(alpha: 0.85)
                : AppColors.gray100,
            borderColor: AppColors.gray300,
            borderStrokeWidth: 0.6,
          ),
    ];
    _staticFootways = [
      for (final w in widget.graph.osm.footways)
        if (w.length >= 2)
          Polyline(
            points: [for (final p in w) LatLng(p[0], p[1])],
            color: AppColors.teal.withValues(alpha: 0.25),
            strokeWidth: 1.0,
          ),
    ];
    _fullRouteLine = [
      Polyline(
        points: routePoints,
        color: AppColors.amber.withValues(alpha: 0.35),
        strokeWidth: 3,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (_routePoints.length < 2 || _bounds == null) {
      return const SizedBox.shrink();
    }

    final activeIdx = widget.activeEdgeIndex.clamp(0, widget.route.length - 1);
    final activeStep = widget.route[activeIdx];
    // Skip the highlight overlay when either endpoint lacks coords — falling
    // back to (0, 0) would draw a phantom marker far outside the campus
    // bounds and stretch the camera fit.
    final activeFrom =
        (activeStep.from.lat != null && activeStep.from.lng != null)
            ? LatLng(activeStep.from.lat!, activeStep.from.lng!)
            : null;
    final activeTo = (activeStep.to.lat != null && activeStep.to.lng != null)
        ? LatLng(activeStep.to.lat!, activeStep.to.lng!)
        : null;

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: RepaintBoundary(
        child: Container(
          color: AppColors.paper,
          child: FlutterMap(
            options: MapOptions(
              interactionOptions:
                  const InteractionOptions(flags: InteractiveFlag.none),
              initialCameraFit: CameraFit.bounds(
                bounds: _bounds!,
                padding: const EdgeInsets.all(16),
              ),
            ),
            children: [
              // Building footprints (cached)
              PolygonLayer(
                polygonCulling: true,
                polygons: _staticPolygons,
              ),
              // Footways — faint (cached)
              PolylineLayer(polylines: _staticFootways),
              // Full route — muted (cached)
              PolylineLayer(polylines: _fullRouteLine),
              // Active edge — bold (recomputed per swipe; tiny)
              if (activeFrom != null && activeTo != null)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: [activeFrom, activeTo],
                      color: AppColors.amber,
                      strokeWidth: 4.5,
                      borderStrokeWidth: 1.5,
                      borderColor: Colors.white,
                    ),
                  ],
                ),
              // Origin / current / destination dots
              MarkerLayer(
                markers: [
                  _dot(_routePoints.first, AppColors.teal, 10),
                  if (activeTo != null) _dot(activeTo, AppColors.amber, 12),
                  _dot(_routePoints.last, AppColors.teal, 10),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static List<LatLng> _computeRoutePoints(List<RouteStep> route) {
    if (route.isEmpty) return const [];
    final pts = <LatLng>[];
    final first = route.first.from;
    if (first.lat != null && first.lng != null) {
      pts.add(LatLng(first.lat!, first.lng!));
    }
    for (final step in route) {
      if (step.to.lat != null && step.to.lng != null) {
        pts.add(LatLng(step.to.lat!, step.to.lng!));
      }
    }
    return pts;
  }

  static Marker _dot(LatLng point, Color color, double size) {
    return Marker(
      point: point,
      width: size + 6,
      height: size + 6,
      child: Container(
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 2),
        ),
      ),
    );
  }
}
