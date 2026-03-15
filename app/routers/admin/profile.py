from fastapi import APIRouter, Request, Depends, Form, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.security.csrf import validate_csrf
from app.routers.admin.admin import guard_router, templates, get_db
from app.services.admin.user_service import UserService
from app.services.admin.resume_service import ResumeService
from app.repositories.admin.user_repository import UserRepository
from app.routers.admin.deps import get_current_user
from app.schemas.admin.auth import ResetPasswordSchema

router = guard_router
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_service(db: AsyncSession = Depends(get_db)):
    return UserService(UserRepository(db))


@router.get('/profile', response_class=HTMLResponse, name='admin.profile.index')
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user(request, db)
    if not user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

    resume_service = ResumeService(db)
    check = await resume_service.can_generate(user.id)

    return templates.TemplateResponse('profile/index.html', {
        'request': request,
        'user': user,
        'can_generate': check['allowed'],
        'generate_reason': check.get('reason', '')
    })


@router.post('/profile/update', name='admin.profile.update', dependencies=[Depends(validate_csrf)])
async def update_profile(
        request: Request,
        first_name: str = Form(...),
        last_name: str = Form(...),
        phone_number: str = Form(None),
        avatar: UploadFile = None,
        service: UserService = Depends(get_service),
        db: AsyncSession = Depends(get_db)
):
    current_user = await get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url='/sirius.achievements/login', status_code=302)

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

    url = request.url_for('admin.profile.index').include_query_params(toast_msg="Профиль обновлен",
                                                                      toast_type="success")
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
