from typing import Generator, Optional, List
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import oauth2_scheme, decode_access_token
from app.models.entities import User

def get_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[User]:
    if not token:
        # Default to viewer for open exploration in prototype if no token supplied
        viewer = db.query(User).filter(User.email == "viewer@insulguard.com").first()
        return viewer
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access credentials"
        )
    
    email = payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: Optional[User] = Depends(get_current_user)) -> User:
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the following roles: {', '.join(allowed_roles)}. Current role: {current_user.role}"
            )
        return current_user
    return role_checker
