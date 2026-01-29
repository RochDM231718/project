from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService, UserBlockedException
from app.routers.admin.admin import templates, get_db
from app.repositories.admin.user_repository import UserRepository
from app.schemas.admin.auth import UserRegister

router = APIRouter(prefix="/admin", tags=["Admin Auth"])


def get_service(db: AsyncSession = Depends(get_db)):
    return AuthService(UserRepository(db))


@router.get('/login', response_class=HTMLResponse, name='admin.auth.login_page')
async def login_page(request: Request):
    if request.session.get('auth_id'):
        return RedirectResponse(url='/admin/dashboard', status_code=302)
    return templates.TemplateResponse('auth/sign-in.html', {'request': request})


@router.post('/login', name='admin.auth.login')
async def login(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        service: AuthService = Depends(get_service)
):
    try:
        user = await service.authenticate(email, password)

        if not user:
            return templates.TemplateResponse('auth/sign-in.html', {
                'request': request,
                'error_msg': "Неверный email или пароль",
                'form_data': {'email': email}
            })

        request.session['auth_id'] = user.id
        request.session['auth_role'] = user.role.value
        request.session['auth_name'] = f"{user.first_name} {user.last_name}"
        request.session['auth_avatar'] = user.avatar_path

        return RedirectResponse(url='/admin/dashboard', status_code=302)

    except UserBlockedException as e:
        return templates.TemplateResponse('auth/sign-in.html', {
            'request': request,
            'error_msg': str(e),
            'form_data': {'email': email}
        })


@router.get('/logout', name='admin.auth.logout')
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/admin/login', status_code=302)


@router.get('/register', response_class=HTMLResponse, name='admin.auth.register_page')
async def register_page(request: Request):
    if request.session.get('auth_id'):
        return RedirectResponse(url='/admin/dashboard', status_code=302)
    return templates.TemplateResponse('auth/register.html', {'request': request})


@router.post('/register', name='admin.auth.register')
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

        # 1. Регистрация (теперь возвращает user)
        user = await service.register_user(user_data)

        # 2. Автоматическая авторизация
        request.session['auth_id'] = user.id
        request.session['auth_role'] = user.role.value
        request.session['auth_name'] = f"{user.first_name} {user.last_name}"
        request.session['auth_avatar'] = user.avatar_path

        # 3. Редирект сразу на Dashboard
        return RedirectResponse(
            url='/admin/dashboard',
            status_code=302
        )
    except ValueError as e:
        error_msg = str(e).split('\n')[0] if '\n' in str(e) else str(e)
        return templates.TemplateResponse('auth/register.html', {
            'request': request,
            'error_msg': "Ошибка данных: " + error_msg,
            'form_data': {'first_name': first_name, 'last_name': last_name, 'email': email}
        })
    except Exception as e:
        return templates.TemplateResponse('auth/register.html', {
            'request': request,
            'error_msg': str(e),
            'form_data': {'first_name': first_name, 'last_name': last_name, 'email': email}
        })


@router.get('/forgot-password', response_class=HTMLResponse, name='admin.auth.forgot_password_page')
async def forgot_password_page(request: Request):
    return templates.TemplateResponse('auth/forgot-password.html', {'request': request})


@router.post('/forgot-password', name='admin.auth.forgot_password')
async def forgot_password(request: Request, email: str = Form(...)):
    return templates.TemplateResponse('auth/forgot-password.html', {
        'request': request,
        'success_msg': "Если аккаунт существует, мы отправили инструкцию на почту."
    })