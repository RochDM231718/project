from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import time
import os
import redis.asyncio as aioredis
import structlog

from app.routers.admin.deps import get_current_user
from app.security.csrf import validate_csrf
from app.services.auth_service import AuthService, UserBlockedException
from app.routers.admin.admin import templates, get_db
from app.repositories.admin.user_repository import UserRepository
from app.repositories.admin.user_token_repository import UserTokenRepository
from app.services.admin.user_token_service import UserTokenService
from app.schemas.admin.auth import UserRegister, ResetPasswordSchema
from app.models.enums import EducationLevel

logger = structlog.get_logger()
redis_client = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)

router = APIRouter(prefix="/sirius.achievements", tags=["Auth"])


def get_service(db: AsyncSession = Depends(get_db)):
    user_repo = UserRepository(db)
    token_repo = UserTokenRepository(db)
    token_service = UserTokenService(token_repo)
    return AuthService(user_repo, token_service)


@router.get('/login', response_class=HTMLResponse, name='admin.auth.login_page')
async def login_page(request: Request):
    if request.session.get('auth_id'):
        return RedirectResponse(url=request.url_for('admin.dashboard.index'), status_code=302)
    return templates.TemplateResponse('auth/sign-in.html', {'request': request})


@router.post('/login', name='admin.auth.login', dependencies=[Depends(validate_csrf)])
async def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        service: AuthService = Depends(get_service)
):
    try:
        client_ip = request.client.host if request.client else "unknown"
        user = await service.authenticate(email, password, ip=client_ip)

        if not user:
            return templates.TemplateResponse('auth/sign-in.html', {
                'request': request,
                'error_msg': "Неверный email или пароль",
                'form_data': {'email': email}
            })

        request.session['auth_id'] = user.id
        request.session['auth_name'] = f"{user.first_name} {user.last_name}"
        request.session['auth_avatar'] = user.avatar_path

        return RedirectResponse(url=request.url_for('admin.dashboard.index'), status_code=302)

    except UserBlockedException as e:
        return templates.TemplateResponse('auth/sign-in.html', {
            'request': request,
            'error_msg': str(e),
            'form_data': {'email': email}
        })


@router.get('/logout', name='admin.auth.logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=request.url_for('admin.auth.login_page'), status_code=302)


@router.get('/register', response_class=HTMLResponse, name='admin.auth.register_page')
async def register_page(request: Request):
    if request.session.get('auth_id'):
        return RedirectResponse(url=request.url_for('admin.dashboard.index'), status_code=302)
    return templates.TemplateResponse('auth/register.html', {
        'request': request,
        'education_levels': list(EducationLevel)
    })


@router.post('/register', name='admin.auth.register', dependencies=[Depends(validate_csrf)])
async def register(
        request: Request,
        first_name: str = Form(...),
        last_name: str = Form(...),
        email: str = Form(...),
        education_level: EducationLevel = Form(...),
        course: int = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
        service: AuthService = Depends(get_service)
):
    form_data = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'education_level': education_level.value,
        'course': course
    }

    if password != password_confirm:
        return templates.TemplateResponse('auth/register.html', {
            'request': request,
            'error_msg': "Пароли не совпадают",
            'form_data': form_data,
            'education_levels': list(EducationLevel)
        })

    try:
        user_data = UserRegister(
            first_name=first_name,
            last_name=last_name,
            email=email,
            education_level=education_level,
            course=course,
            password=password,
            password_confirm=password_confirm
        )

        user = await service.register_user(user_data)

        request.session['auth_id'] = user.id
        request.session['auth_name'] = f"{user.first_name} {user.last_name}"
        request.session['auth_avatar'] = user.avatar_path

        return RedirectResponse(url=request.url_for('admin.dashboard.index'), status_code=302)
    except Exception as e:
        return templates.TemplateResponse('auth/register.html', {
            'request': request,
            'error_msg': str(e),
            'form_data': form_data,
            'education_levels': list(EducationLevel)
        })


@router.get('/forgot-password', response_class=HTMLResponse, name='admin.auth.forgot_password_page')
async def forgot_password_page(request: Request):
    return templates.TemplateResponse('auth/forgot-password.html', {'request': request})


@router.post('/forgot-password', name='admin.auth.forgot_password', dependencies=[Depends(validate_csrf)])
async def forgot_password(
        request: Request,
        background_tasks: BackgroundTasks,
        email: str = Form(...),
        service: AuthService = Depends(get_service)
):
    success, msg, retry_after = await service.forgot_password(email, background_tasks)

    if not success:
        return templates.TemplateResponse('auth/forgot-password.html', {
            'request': request,
            'error_msg': msg
        })

    request.session['reset_email'] = email
    request.session['retry_at'] = int(time.time()) + retry_after

    return RedirectResponse(url=request.url_for('admin.auth.verify_code_page'), status_code=302)


@router.get('/verify-code', response_class=HTMLResponse, name='admin.auth.verify_code_page')
async def verify_code_page(request: Request):
    email = request.session.get('reset_email')
    if not email:
        return RedirectResponse(url=request.url_for('admin.auth.forgot_password_page'), status_code=302)

    retry_at = request.session.get('retry_at', 0)
    now = int(time.time())
    seconds_left = max(0, retry_at - now)

    return templates.TemplateResponse('auth/verify-code.html', {
        'request': request,
        'email': email,
        'seconds_left': seconds_left
    })


@router.post('/resend-code', name='admin.auth.resend_code', dependencies=[Depends(validate_csrf)])
async def resend_code(
        request: Request,
        background_tasks: BackgroundTasks,
        service: AuthService = Depends(get_service)
):
    email = request.session.get('reset_email')
    if not email:
        return RedirectResponse(url=request.url_for('admin.auth.forgot_password_page'), status_code=302)

    success, msg, retry_after = await service.forgot_password(email, background_tasks)

    if success:
        request.session['retry_at'] = int(time.time()) + retry_after

    return RedirectResponse(url=request.url_for('admin.auth.verify_code_page'), status_code=302)


@router.post('/verify-code', name='admin.auth.verify_code', dependencies=[Depends(validate_csrf)])
async def verify_code(
        request: Request,
        code: str = Form(...),
        service: AuthService = Depends(get_service)
):
    email = request.session.get('reset_email')
    retry_at = request.session.get('retry_at', 0)
    seconds_left = max(0, retry_at - int(time.time()))

    if not email:
        return RedirectResponse(url=request.url_for('admin.auth.forgot_password_page'), status_code=302)

    # Rate-limit: max 5 OTP attempts per email per 15 minutes
    rl_key = f"otp_attempts:{email}"
    attempts = await redis_client.get(rl_key)
    if attempts and int(attempts) >= 5:
        return templates.TemplateResponse('auth/verify-code.html', {
            'request': request,
            'email': email,
            'error_msg': "Слишком много попыток. Запросите новый код через 15 минут.",
            'seconds_left': seconds_left
        })

    try:
        await service.verify_code_only(email, code)
        await redis_client.delete(rl_key)
        request.session['code_verified'] = True
        return RedirectResponse(url=request.url_for('admin.auth.reset_password_page'), status_code=302)

    except Exception as e:
        await redis_client.incr(rl_key)
        if await redis_client.ttl(rl_key) == -1:
            await redis_client.expire(rl_key, 900)

        remaining = 5 - (int(await redis_client.get(rl_key) or 0))
        error_msg = "Неверный код. Попробуйте еще раз."
        if remaining <= 2:
            error_msg = f"Неверный код. Осталось попыток: {remaining}."

        return templates.TemplateResponse('auth/verify-code.html', {
            'request': request,
            'email': email,
            'error_msg': error_msg,
            'seconds_left': seconds_left
        })


@router.get('/reset-password', response_class=HTMLResponse, name='admin.auth.reset_password_page')
async def reset_password_page(request: Request):
    if not request.session.get('code_verified') or not request.session.get('reset_email'):
        return RedirectResponse(url=request.url_for('admin.auth.forgot_password_page'), status_code=302)

    return templates.TemplateResponse('auth/reset-password.html', {'request': request})


@router.post('/reset-password', name='admin.auth.reset_password', dependencies=[Depends(validate_csrf)])
async def reset_password(
        request: Request,
        password: str = Form(...),
        password_confirm: str = Form(...),
        service: AuthService = Depends(get_service)
):
    email = request.session.get('reset_email')
    if not email or not request.session.get('code_verified'):
        return RedirectResponse(url=request.url_for('admin.auth.forgot_password_page'), status_code=302)

    try:
        ResetPasswordSchema(password=password, password_confirm=password_confirm)
    except Exception as e:
        error_messages = []
        if hasattr(e, 'errors'):
            for err in e.errors():
                error_messages.append(err.get('msg', str(err)))
        else:
            error_messages.append(str(e))
        return templates.TemplateResponse('auth/reset-password.html', {
            'request': request,
            'error_msg': "; ".join(error_messages)
        })

    try:
        await service.reset_password_final(email, password)

        request.session.pop('reset_email', None)
        request.session.pop('retry_at', None)
        request.session.pop('code_verified', None)

        return templates.TemplateResponse('auth/sign-in.html', {
            'request': request,
            'success_msg': "Пароль успешно изменен. Войдите в систему."
        })
    except Exception as e:
        logger.error("Password reset failed", error=str(e))
        return templates.TemplateResponse('auth/reset-password.html', {
            'request': request,
            'error_msg': "Произошла ошибка при смене пароля"
        })