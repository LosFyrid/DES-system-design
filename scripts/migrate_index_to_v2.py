#!/usr/bin/env python3
"""
Migrate index.json to v2 format (one-time script)

This script upgrades the existing index.json to include new fields
required for fast list operations:
- formulation_summary: Human-readable formulation string
- formulation: Full formulation dictionary
- confidence: Confidence score
- performance_score: Performance score from experiment result

Usage:
    python scripts/migrate_index_to_v2.py
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent.reasoningbank.feedback import RecommendationManager, Recommendation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_index():
    """Migrate index.json to v2 format with new fields"""

    # Initialize recommendation manager
    rec_manager = RecommendationManager(storage_path="data/recommendations")

    logger.info(f"Starting index migration for {len(rec_manager.index)} recommendations")

    # Track statistics
    migrated = 0
    skipped = 0
    errors = 0

    # Backup original index
    backup_file = rec_manager.storage_path / f"index_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(rec_manager.index, f, indent=2, ensure_ascii=False)
    logger.info(f"Created backup: {backup_file}")

    # Migrate each recommendation
    for rec_id, meta in list(rec_manager.index.items()):
        try:
            # Check if already migrated (has new fields)
            if "formulation" in meta and "confidence" in meta:
                logger.debug(f"Skipping {rec_id} - already migrated")
                skipped += 1
                continue

            # Load full recommendation
            rec = rec_manager.get_recommendation(rec_id)
            if not rec:
                logger.warning(f"Could not load recommendation: {rec_id}")
                errors += 1
                continue

            # Update index entry with new fields
            rec_manager.index[rec_id].update({
                "formulation_summary": rec_manager._get_formulation_summary(rec.formulation),
                "formulation": rec.formulation,
                "confidence": rec.confidence,
                "performance_score": rec.experiment_result.get_performance_score() if rec.experiment_result else None,
            })

            migrated += 1
            logger.info(f"Migrated {rec_id}")

        except Exception as e:
            logger.error(f"Error migrating {rec_id}: {e}", exc_info=True)
            errors += 1

    # Save updated index
    rec_manager._save_index()
    logger.info(f"Saved updated index to {rec_manager.index_file}")

    # Print summary
    logger.info("=" * 60)
    logger.info("Migration Summary:")
    logger.info(f"  Total recommendations: {len(rec_manager.index)}")
    logger.info(f"  Migrated: {migrated}")
    logger.info(f"  Skipped (already migrated): {skipped}")
    logger.info(f"  Errors: {errors}")
    logger.info(f"  Backup saved to: {backup_file}")
    logger.info("=" * 60)

    if errors > 0:
        logger.warning(f"Migration completed with {errors} errors - please review")
        return False
    else:
        logger.info("Migration completed successfully!")
        return True


if __name__ == "__main__":
    logger.info("Index Migration Script v2.0")
    logger.info("=" * 60)

    success = migrate_index()

    if success:
        logger.info("✓ All recommendations migrated successfully")
        sys.exit(0)
    else:
        logger.error("✗ Migration completed with errors")
        sys.exit(1)
