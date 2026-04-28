import sys
import logging
from sqlalchemy.orm import Session
from database import SessionLocal
from models.core import User
from auth import pwd_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def promote_or_create_admin(identifier: str, password: str = None):
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()
        
        if user:
            user.is_platform_admin = True
            user.role = "admin"
            logger.info(f"Promoted existing user {identifier} to Platform Admin.")
        else:
            if not password:
                logger.error("User not found and no password provided to create new admin.")
                sys.exit(1)
            
            is_email = "@" in identifier
            email = identifier if is_email else f"{identifier}@admin.local"
            username = identifier if not is_email else identifier.split("@")[0]
            
            user = User(
                email=email,
                username=username,
                hashed_password=pwd_context.hash(password),
                role="admin",
                is_platform_admin=True,
                organization_id=None  # Platform admins don't need a specific org
            )
            db.add(user)
            logger.info(f"Created new Platform Admin: {identifier}")
            
        db.commit()
    except Exception as e:
        logger.error(f"Failed: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_admin.py <email_or_username> [password_if_new]")
        sys.exit(1)
        
    identifier = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else None
    
    if password and len(password) < 8:
        print("Error: Password must be at least 8 characters long.")
        sys.exit(1)
        
    print(f"\nTarget Identifier: {identifier}")
    confirm = input("Are you sure you want to create/promote this user to platform admin? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        sys.exit(0)
        
    promote_or_create_admin(identifier, password)
