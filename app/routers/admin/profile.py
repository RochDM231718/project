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


@router.get('/profile', response_class=HTMLResponse, name='admin.profile.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get('auth_id')

    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    stmt = select(Users).options(selectinload(Users.achievements)).where(Users.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

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

    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    # 1. Получаем текущего пользователя (нужен для рендеринга шаблона при ошибке)
    stmt = select(Users).options(selectinload(Users.achievements)).where(Users.id == user_id)
    result = await db.execute(stmt)
    current_user = result.scalars().first()

    if not current_user:
        request.session.clear()
        return RedirectResponse(url='/admin/login', status_code=302)

    # 2. Проверка email
    stmt_email = select(Users).filter(Users.email == email)
    result_email = await db.execute(stmt_email)
    existing = result_email.scalars().first()

    # Если email занят другим пользователем
    if existing and existing.id != user_id:
        # Временно обновляем объект для отображения в форме (не сохраняя в БД)
        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.email = email
        current_user.phone_number = phone_number

        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': current_user,  # Передаем объект с введенными данными
            'error_msg': "Email уже занят",
            'active_tab': 'profile'  # Указываем вкладку
        })

    update_data = {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone_number": phone_number
    }

    # 3. Обработка аватара
    if avatar and avatar.filename:
        try:
            path = await service.save_avatar(user_id, avatar)
            update_data["avatar_path"] = path
            request.session['auth_avatar'] = path
        except ValueError as e:
            # При ошибке валидации файла также возвращаем форму с данными
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

    # 4. Сохранение изменений
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

    if not user_id:
        return RedirectResponse(url='/admin/login', status_code=302)

    # Получаем пользователя для проверки пароля и рендеринга
    stmt = select(Users).options(selectinload(Users.achievements)).where(Users.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        request.session.clear()
        return RedirectResponse(url='/admin/login', status_code=302)

    # Проверка совпадения новых паролей
    if new_password != confirm_password:
        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': user,
            'error_msg': "Пароли не совпадают",
            'active_tab': 'security'
        })

    # Проверка текущего пароля
    if not pwd_context.verify(current_password, user.hashed_password):
        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': user,
            'error_msg': "Неверный текущий пароль",
            'active_tab': 'security'
        })

    # Смена пароля
    user.hashed_password = pwd_context.hash(new_password)
    await db.commit()

    url = request.url_for('admin.profile.index').include_query_params(
        toast_msg="Пароль изменен",
        toast_type="success",
        active_tab="security"
    )
    return RedirectResponse(url=url, status_code=302)