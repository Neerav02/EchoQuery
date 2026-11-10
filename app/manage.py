import sys
import os
import argparse
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, Base, engine
import models
from security import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echoquery.manage")

def bootstrap_admin(email: str, password: str, force: bool = False):
    """Bootstraps the primary system administrator account."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == email).first()
        if existing:
            if not force:
                logger.info(f"User '{email}' already exists. Use --force to update privileges to superuser.")
                return False
            existing.hashed_password = hash_password(password)
            existing.is_superuser = True
            existing.password_migrated = True
            db.commit()
            logger.info(f"Superuser '{email}' successfully updated.")
            return True

        admin_user = models.User(
            email=email,
            hashed_password=hash_password(password),
            is_superuser=True,
            password_migrated=True
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Primary administrator '{email}' successfully bootstrapped.")
        return True
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description="EchoQuery Administrative CLI")
    subparsers = parser.add_subparsers(dest="command")

    admin_parser = subparsers.add_parser("bootstrap-admin", help="Bootstrap initial system administrator")
    admin_parser.add_argument("--email", required=True, help="Administrator email address")
    admin_parser.add_argument("--password", required=True, help="Administrator password")
    admin_parser.add_argument("--force", action="store_true", help="Force upgrade existing account to superuser")

    args = parser.parse_args()

    if args.command == "bootstrap-admin":
        bootstrap_admin(args.email, args.password, args.force)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

