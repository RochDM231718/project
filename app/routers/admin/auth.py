from fastapi import APIRouter, Request, Depends, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.routers.admin.deps import get_current_user
from app.security.csrf import validate_csrf
from app.services.auth_service import AuthService, UserBlockedException
from app.routers.admin.admin import templates, get_db
from app.repositories.admin.user_repository import UserRepository
from app.repositories.admin.user_token_repository import UserTokenRepository
from app.services.admin.user_token_service import UserTokenService
from app.schemas.admin.auth import UserRegister

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
    return templates.TemplateResponse('auth/register.html', {'request': request})


@router.post('/register', name='admin.auth.register', dependencies=[Depends(validate_csrf)])
async def register(
        request: Request,
        first_name: str = Form(...),
        last_name: str = Form(...),
        email: str = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
        service: AuthService = Depends(get_service)
):
    if password != password_confirm:
        return templates.TemplateResponse('auth/register.html', {
            'request': request,
            'error_msg': "Пароли не совпадают",
            'form_data': {'first_name': first_name, 'last_name': last_name, 'email': email}
        })

    try:
        user_data = UserRegister(
            first_name=first_name,
            last_name=last_name,
            email=email,
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
            'form_data': {'first_name': first_name, 'last_name': last_name, 'email': email}
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

    try:
        await service.verify_code_only(email, code)
        request.session['code_verified'] = True
        return RedirectResponse(url=request.url_for('admin.auth.reset_password_page'), status_code=302)

    except Exception as e:
        return templates.TemplateResponse('auth/verify-code.html', {
            'request': request,
            'email': email,
            'error_msg': "Неверный код. Попробуйте еще раз.",
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

    if password != password_confirm:
        return templates.TemplateResponse('auth/reset-password.html', {
            'request': request,
            'error_msg': "Пароли не совпадают"
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
        return templates.TemplateResponse('auth/reset-password.html', {
            'request': request,
            'error_msg': "Ошибка при смене пароля: " + str(e)
        })