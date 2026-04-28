import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.database import SessionLocal
from database.models import User
from schema.auth import SignupRequest, LoginRequest, AuthResponse, ChangePasswordRequest
from auth.utils import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": user.username,
        "email": user.email,
        "user_id": user.id,
        "role": user.role,
    })
    return AuthResponse(
        access_token=token,
        username=user.username,
        email=user.email,
        role=user.role,
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Username atau password salah")

    token = create_access_token({
        "sub": user.username,
        "email": user.email,
        "user_id": user.id,
        "role": user.role,
    })
    return AuthResponse(
        access_token=token,
        username=user.username,
        email=user.email,
        role=user.role,
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    body: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password saat ini salah")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password baru minimal 6 karakter")

    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password berhasil diubah"}


@router.post("/admin/create", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def create_admin(body: SignupRequest, secret: str, db: Session = Depends(get_db)):
    """
    Endpoint khusus untuk membuat akun admin.
    Butuh query param ?secret=<ADMIN_SECRET> yang di-set di .env
    """
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Secret tidak valid")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimal 6 karakter")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({
        "sub": user.username,
        "email": user.email,
        "user_id": user.id,
        "role": user.role,
    })
    return AuthResponse(
        access_token=token,
        username=user.username,
        email=user.email,
        role=user.role,
    )
