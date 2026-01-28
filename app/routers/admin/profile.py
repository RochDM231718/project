from fastapi import APIRouter, Request, Depends, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository

router = guard_router
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


# ... метод index ...
@router.get('/profile', response_class=HTMLResponse, name='admin.profile.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')

    # [FIX] Добавлена проверка на наличие user_id в сессии
    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    stmt = select(Users).options(selectinload(Users.achievements)).where(Users.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # [FIX] Если пользователя нет в БД (например, удален), а сессия осталась - разлогиниваем
    if not user:
        request.session.clear()
        return RedirectResponse(url='/admin/login', status_code=302)

    return templates.TemplateResponse('profile/index.html', {'request': request, 'user': user})


@router.post('/profile/update', name='admin.profile.update')
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
    user_id = request.session.get('auth_id')

    # [FIX] Добавлена проверка на наличие user_id
    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    # Проверка email
    stmt = select(Users).filter(Users.email == email)
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing and existing.id != user_id:
        return RedirectResponse(url="/admin/profile?active_tab=profile&error_msg=Email уже занят", status_code=302)

    update_data = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number
    }

    if avatar and avatar.filename:
        try:
            # Пытаемся сохранить аватар (тут сработают проверки)
            path = await service.save_avatar(user_id, avatar)
            update_data["avatar_path"] = path
            request.session['auth_avatar'] = path
        except ValueError as e:
            # Если размер/тип не тот, возвращаем ошибку
            return RedirectResponse(
                url=f"/admin/profile?active_tab=profile&error_msg={str(e)}",
                status_code=302
            )

    await service.repository.update(user_id, update_data)
    request.session['auth_name'] = f"{first_name} {last_name}"

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Профиль обновлен",
                                                                      toast_type="success")
    return RedirectResponse(url=url, status_code=302)


@router.post('/profile/password', name='admin.profile.password')
async def change_password(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        confirm_password: str = Form(...),
        db: AsyncSession = Depends(get_db)
):
    user_id = request.session.get('auth_id')

    # [FIX] Добавлена проверка
    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    if new_password != confirm_password:
        return RedirectResponse(url="/admin/profile?active_tab=security&error_msg=Пароли не совпадают", status_code=302)

    stmt = select(Users).where(Users.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # [FIX] Еще одна проверка на существование юзера
    if not user:
        request.session.clear()
        return RedirectResponse(url='/admin/login', status_code=302)

    if not pwd_context.verify(current_password, user.hashed_password):
        return RedirectResponse(url="/admin/profile?active_tab=security&error_msg=Неверный текущий пароль",
                                status_code=302)
    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()
    return RedirectResponse(url="/admin/profile?active_tab=security&toast_msg=Пароль изменен&toast_type=success",
                            status_code=302)