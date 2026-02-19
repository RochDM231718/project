from fastapi import APIRouter, Request, Depends, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository
from app.routers.admin.deps import get_current_user

router = guard_router
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))

@router.get('/profile', response_class=HTMLResponse, name='admin.profile.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    return templates.TemplateResponse('profile/index.html', {'request': request, 'user': user})

@router.post('/profile/update', name='admin.profile.update', dependencies=[Depends(validate_csrf)])
async def update_profile(
        request: Request,
        first_name: str = Form(...),
        last_name: str = Form(...),
        email: str = Form(...),
        phone_number: str = Form(None),
        avatar: UploadFile = None,
        service: UserService = Depends(get_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    # Проверка email
    stmt_email = select(Users).filter(Users.email == email)
    result_email = await db.execute(stmt_email)
    existing = result_email.scalars().first()

    if existing and existing.id != current_user.id:
        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.email = email
        current_user.phone_number = phone_number

        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': current_user,
            'error_msg': "Email уже занят",
            'active_tab': 'profile'
        })

    update_data = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number
    }

    if avatar and avatar.filename:
        try:
            path = await service.save_avatar(current_user.id, avatar)
            update_data["avatar_path"] = path
            request.session['auth_avatar'] = path
        except ValueError as e:
            current_user.first_name = first_name
            current_user.last_name = last_name
            current_user.email = email
            current_user.phone_number = phone_number
            return templates.TemplateResponse('profile/index.html', {
                'request': request,
                'user': current_user,
                'error_msg': str(e),
                'active_tab': 'profile'
            })

    await service.repository.update(current_user.id, update_data)
    request.session['auth_name'] = f"{first_name} {last_name}"

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Профиль обновлен", toast_type="success")
    return RedirectResponse(url=url, status_code=302)

@router.post('/profile/password', name='admin.profile.password', dependencies=[Depends(validate_csrf)])
async def change_password(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        confirm_password: str = Form(...),
        db: AsyncSession = Depends(get_db)
):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    if new_password != confirm_password:
        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': user,
            'error_msg': "Пароли не совпадают",
            'active_tab': 'security'
        })

    if not pwd_context.verify(current_password, user.hashed_password):
        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': user,
            'error_msg': "Неверный текущий пароль",
            'active_tab': 'security'
        })

    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Пароль изменен", toast_type="success", active_tab="security")
    return RedirectResponse(url=url, status_code=302)