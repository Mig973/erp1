from sqlalchemy.orm import Session

from . import models, schemas
from .security import get_password_hash


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(email=user.email, hashed_password=hashed_password)

    # Assign a default role
    default_role = get_role_by_name(db, name="user")
    if not default_role:
        default_role = create_role(db, role=schemas.RoleCreate(name="user"))

    db_user.roles.append(default_role)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_role_by_name(db: Session, name: str):
    return db.query(models.Role).filter(models.Role.name == name).first()


def create_role(db: Session, role: schemas.RoleCreate):
    db_role = models.Role(name=role.name)
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role


def assign_role_to_user(db: Session, user: models.User, role: models.Role):
    user.roles.append(role)
    db.commit()
    db.refresh(user)
    return user
