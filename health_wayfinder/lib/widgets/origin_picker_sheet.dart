import 'package:flutter/material.dart';

import '../l10n/generated/app_localizations.dart';
import '../models/topology.dart';
import '../theme.dart';

/// Modal sheet shown when GPS is denied / unavailable / off the map.
/// Lists parking, entrance, and transit nodes from the topology so the
/// patient can declare where they're starting from. Selection becomes
/// `ConversationState.currentLocation` and feeds Dijkstra as the origin.
class OriginPickerSheet extends StatelessWidget {
  final CampusGraph graph;

  const OriginPickerSheet({super.key, required this.graph});

  static Future<TopologyNode?> show(
    BuildContext context, {
    required CampusGraph graph,
  }) {
    return showModalBottomSheet<TopologyNode>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => OriginPickerSheet(graph: graph),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final candidates = graph.nodes.values
        .where((n) =>
            n.type == NodeType.parking ||
            n.type == NodeType.entrance ||
            n.type == NodeType.transit)
        .where((n) => n.label.trim().isNotEmpty)
        .toList()
      ..sort((a, b) {
        // Parking first, then entrance, then transit; alphabetical within group.
        final order = {
          NodeType.parking: 0,
          NodeType.entrance: 1,
          NodeType.transit: 2,
        };
        final cmp = (order[a.type] ?? 9).compareTo(order[b.type] ?? 9);
        if (cmp != 0) return cmp;
        return a.label.compareTo(b.label);
      });

    return SafeArea(
      child: Container(
        decoration: BoxDecoration(
          color: context.surfaceColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: context.textMuted.withValues(alpha: 0.4),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              l10n.originPickerTitle,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w700,
                color: context.textPrimary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              l10n.originPickerSubtitle,
              style: TextStyle(fontSize: 14, color: context.textMuted),
            ),
            const SizedBox(height: 16),
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(context).size.height * 0.5,
              ),
              child: SingleChildScrollView(
                child: Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    for (final node in candidates)
                      _OriginChip(
                        node: node,
                        onTap: () => Navigator.of(context).pop(node),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(l10n.originPickerSkip),
            ),
          ],
        ),
      ),
    );
  }
}

class _OriginChip extends StatelessWidget {
  final TopologyNode node;
  final VoidCallback onTap;
  const _OriginChip({required this.node, required this.onTap});

  IconData get _icon {
    switch (node.type) {
      case NodeType.parking:
        return Icons.local_parking;
      case NodeType.entrance:
        return Icons.door_front_door;
      case NodeType.transit:
        return Icons.directions_transit;
      default:
        return Icons.place;
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: context.chipBg,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: context.inputBorder, width: 1.2),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_icon, size: 16, color: AppColors.teal),
            const SizedBox(width: 6),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 220),
              child: Text(
                node.label,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: context.textPrimary,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
