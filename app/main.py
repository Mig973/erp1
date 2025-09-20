from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from . import crud, models, schemas, security
from .database import SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db=db, user=user)


@app.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# Instantiate the role checker for admin-only endpoints
# In a real app, the "admin" role would be created via a migration or a seed script.
# For simplicity, we ensure it exists when the app starts.
@app.on_event("startup")
def startup_event():
    with SessionLocal() as db:
        admin_role = crud.get_role_by_name(db, name="admin")
        if not admin_role:
            crud.create_role(db, role=schemas.RoleCreate(name="admin"))
        user_role = crud.get_role_by_name(db, name="user")
        if not user_role:
            crud.create_role(db, role=schemas.RoleCreate(name="user"))

admin_role_checker = security.RoleChecker(["admin"])


@app.get("/users/me", response_model=schemas.User)
async def read_users_me(
    current_user: models.User = Depends(security.get_current_active_user),
):
    return current_user


@app.post("/roles/", response_model=schemas.Role, dependencies=[Depends(admin_role_checker)])
def create_role(role: schemas.RoleCreate, db: Session = Depends(get_db)):
    db_role = crud.get_role_by_name(db, name=role.name)
    if db_role:
        raise HTTPException(status_code=400, detail="Role already exists")
    return crud.create_role(db=db, role=role)


@app.post("/users/{user_email}/roles", response_model=schemas.User, dependencies=[Depends(admin_role_checker)])
def assign_role_to_user(
    user_email: str, role_name: str, db: Session = Depends(get_db)
):
    user = crud.get_user_by_email(db, email=user_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = crud.get_role_by_name(db, name=role_name)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Check if user already has the role
    if role in user.roles:
        raise HTTPException(status_code=400, detail="User already has this role")

    return crud.assign_role_to_user(db=db, user=user, role=role)
