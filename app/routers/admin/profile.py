from fastapi import APIRouter, Request, Depends, Form, UploadFile, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.context import CryptContext
import secrets
import os
import redis.asyncio as aioredis

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.models.user import Users
from app.models.enums import UserStatus
from app.services.admin.user_service import UserService
from app.repositories.admin.user_repository import UserRepository
from app.routers.admin.deps import get_current_user
from app.schemas.admin.auth import ResetPasswordSchema

# Импорты для отправки почты
from app.services.auth_service import AuthService
from app.services.admin.user_token_service import UserTokenService
from app.repositories.admin.user_token_repository import UserTokenRepository

router = guard_router
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

redis_client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)

EMAIL_CODE_TTL = 600  # 10 minutes
EMAIL_CODE_MAX_ATTEMPTS = 5


def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


def get_auth_service(db: AsyncSession = Depends(get_db)):
    return AuthService(UserRepository(db), UserTokenService(UserTokenRepository(db)))


@router.get('/profile', response_class=HTMLResponse, name='admin.profile.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    return templates.TemplateResponse('profile/index.html', {
        'request': request,
        'user': user
    })


@router.post('/profile/update', name='admin.profile.update', dependencies=[Depends(validate_csrf)])
async def update_profile(
        request: Request,
        background_tasks: BackgroundTasks,
        first_name: str = Form(...),
        last_name: str = Form(...),
        email: str = Form(...),
        phone_number: str = Form(None),
        avatar: UploadFile = None,
        service: UserService = Depends(get_service),
        auth_service: AuthService = Depends(get_auth_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    requires_verification = False

    # Если почта изменилась, запускаем процесс верификации
    if email != current_user.email:
        # Сначала проверяем, не занята ли новая почта
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
                'error_msg': "Этот Email уже занят другим пользователем",
                'active_tab': 'profile'
            })

        # Store verification code in Redis (not in session cookie)
        code = ''.join(secrets.choice('0123456789') for _ in range(6))
        redis_key = f"email_change:{current_user.id}"
        await redis_client.hset(redis_key, mapping={"email": email, "code": code, "attempts": "0"})
        await redis_client.expire(redis_key, EMAIL_CODE_TTL)

        # Flag in session that verification is pending (no secrets stored)
        request.session['pending_email_change'] = True

        # Шаблон письма
        subject = "Подтверждение новой почты | Sirius.Achievements"
        text_content = f"Ваш код для подтверждения новой почты: {code}"
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; color: #333;">
            <h2 style="color: #4f46e5;">Изменение почты</h2>
            <p>Вы запросили привязку этого адреса к вашему аккаунту Sirius.Achievements.</p>
            <p>Ваш код подтверждения: <strong style="font-size: 20px; color: #1e293b; background: #f1f5f9; padding: 5px 10px; border-radius: 5px;">{code}</strong></p>
            <p style="color: #64748b; font-size: 12px; margin-top: 20px;">Если это были не вы, проигнорируйте это письмо.</p>
        </div>
        """
        # Отправляем письмо в фоне (чтобы страница не зависла при загрузке)
        background_tasks.add_task(auth_service._send_mail_task, email, subject, text_content, html_content)
        requires_verification = True

    # Обновляем остальные данные (Имя, телефон) сразу
    update_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number
    }

    if avatar and avatar.filename:
        try:
            path = await service.save_avatar(current_user.id, avatar)
            update_data["avatar_path"] = path
            request.session['auth_avatar'] = path
        except ValueError as e:
            return templates.TemplateResponse('profile/index.html', {
                'request': request,
                'user': current_user,
                'error_msg': str(e),
                'active_tab': 'profile'
            })

    await service.repository.update(current_user.id, update_data)
    request.session['auth_name'] = f"{first_name} {last_name}"

    # Если меняли почту — перекидываем на страницу ввода кода
    if requires_verification:
        return RedirectResponse(url=request.url_for('admin.profile.verify_email_page'), status_code=302)

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Профиль обновлен",
                                                                      toast_type="success")
    return RedirectResponse(url=url, status_code=302)


@router.get('/profile/verify-email', response_class=HTMLResponse, name='admin.profile.verify_email_page')
async def verify_email_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)

    redis_key = f"email_change:{user.id}"
    pending_email = await redis_client.hget(redis_key, "email")

    if not pending_email:
        return RedirectResponse(url=request.url_for('admin.profile.index'), status_code=302)

    return templates.TemplateResponse('profile/verify-email.html', {
        'request': request,
        'user': user,
        'pending_email': pending_email
    })


@router.post('/profile/verify-email', name='admin.profile.verify_email_submit', dependencies=[Depends(validate_csrf)])
async def verify_email_submit(
        request: Request,
        code: str = Form(...),
        service: UserService = Depends(get_service),
        db: AsyncSession = Depends(get_db)
):
    user = await get_current_user(request, db)
    redis_key = f"email_change:{user.id}"
    data = await redis_client.hgetall(redis_key)

    if not data or "email" not in data or "code" not in data:
        return RedirectResponse(url=request.url_for('admin.profile.index'), status_code=302)

    pending_email = data["email"]
    valid_code = data["code"]
    attempts = int(data.get("attempts", 0))

    # Rate limit: max attempts
    if attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        await redis_client.delete(redis_key)
        request.session.pop('pending_email_change', None)
        url = request.url_for('admin.profile.index').include_query_params(
            toast_msg="Слишком много попыток. Запросите смену почты заново.", toast_type="error")
        return RedirectResponse(url=url, status_code=302)

    if not secrets.compare_digest(code.strip(), valid_code):
        await redis_client.hincrby(redis_key, "attempts", 1)
        remaining = EMAIL_CODE_MAX_ATTEMPTS - attempts - 1
        error_msg = "Неверный код. Попробуйте еще раз."
        if remaining <= 2:
            error_msg = f"Неверный код. Осталось попыток: {remaining}."
        return templates.TemplateResponse('profile/verify-email.html', {
            'request': request,
            'user': user,
            'pending_email': pending_email,
            'error_msg': error_msg
        })

    # Код верный! Обновляем почту в базе
    await service.repository.update(user.id, {"email": pending_email})

    # Очищаем Redis и сессию
    await redis_client.delete(redis_key)
    request.session.pop('pending_email_change', None)

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Email успешно изменен",
                                                                      toast_type="success")
    return RedirectResponse(url=url, status_code=302)


@router.get('/profile/cancel-email-change', name='admin.profile.cancel_email')
async def cancel_email_change(request: Request, db: AsyncSession = Depends(get_db)):
    """Позволяет отменить смену почты, если пользователь ошибся в адресе или не дождался письма"""
    user = await get_current_user(request, db)
    if user:
        await redis_client.delete(f"email_change:{user.id}")
    request.session.pop('pending_email_change', None)
    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Смена почты отменена",
                                                                      toast_type="error")
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

    try:
        ResetPasswordSchema(password=new_password, password_confirm=confirm_password)
    except Exception as e:
        error_messages = []
        if hasattr(e, 'errors'):
            for err in e.errors():
                error_messages.append(err.get('msg', str(err)))
        else:
            error_messages.append(str(e))
        return templates.TemplateResponse('profile/index.html', {
            'request': request,
            'user': user,
            'error_msg': "; ".join(error_messages),
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

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Пароль изменен", toast_type="success",
                                                                      active_tab="security")
    return RedirectResponse(url=url, status_code=302)
