#!/usr/bin/env python3
"""
Script to populate UIDs for existing records.

This script generates coolname-based UIDs for all existing records that don't
have one yet. Run this after the migration that adds the uid columns.

Usage:
    docker-compose exec web python scripts/populate_uids.py
"""

import sys
import os

# Add the parent directory to the path so we can import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models.quiz import Quiz, QuizResponse
from app.models.user import User
from app.models.group import Group
from app.models.interview import Interview, InterviewSession


def populate_model_uids(model_class, model_name):
    """Populate UIDs for a specific model."""
    records = model_class.query.filter(model_class.uid.is_(None)).all()
    count = len(records)

    if count == 0:
        print(f"  {model_name}: No records need UIDs")
        return 0

    print(f"  {model_name}: Populating {count} records...")

    for i, record in enumerate(records):
        record.uid = model_class.generate_uid()
        if (i + 1) % 100 == 0:
            print(f"    Processed {i + 1}/{count}...")

    db.session.commit()
    print(f"  {model_name}: Done ({count} records updated)")
    return count


def main():
    """Main function to populate all UIDs."""
    app = create_app()

    with app.app_context():
        print("=" * 50)
        print("Populating UIDs for existing records")
        print("=" * 50)

        total = 0

        # Order matters for performance (smaller tables first)
        models = [
            (User, "Users"),
            (Group, "Groups"),
            (Quiz, "Quizzes"),
            (Interview, "Interviews"),
            (QuizResponse, "QuizResponses"),
            (InterviewSession, "InterviewSessions"),
        ]

        for model_class, model_name in models:
            total += populate_model_uids(model_class, model_name)

        print("=" * 50)
        print(f"Total records updated: {total}")
        print("=" * 50)

        # Verify no NULL UIDs remain
        print("\nVerification:")
        all_good = True
        for model_class, model_name in models:
            null_count = model_class.query.filter(model_class.uid.is_(None)).count()
            if null_count > 0:
                print(f"  WARNING: {model_name} still has {null_count} records without UIDs")
                all_good = False
            else:
                print(f"  OK: {model_name} - all records have UIDs")

        if all_good:
            print("\nAll records have been populated with UIDs!")
            print("You can now run the migration to make the uid column NOT NULL.")
        else:
            print("\nWARNING: Some records are still missing UIDs. Please investigate.")


if __name__ == '__main__':
    main()
