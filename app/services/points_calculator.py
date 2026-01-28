from app.models.enums import AchievementLevel, AchievementCategory


def calculate_points(level: str, category: str) -> int:
    """
    Рассчитывает количество баллов на основе уровня и категории.
    """

    # Базовые очки за уровень
    level_points = {
        AchievementLevel.SCHOOL.value: 10,  # Школьный
        AchievementLevel.MUNICIPAL.value: 20,  # Муниципальный
        AchievementLevel.REGIONAL.value: 40,  # Региональный
        AchievementLevel.FEDERAL.value: 75,  # Всероссийский
        AchievementLevel.INTERNATIONAL.value: 100  # Международный
    }

    points = level_points.get(level, 10)

    # Можно добавить коэффициенты для категорий (опционально)
    # Например, за Науку давать на 10% больше:
    # if category == AchievementCategory.SCIENCE.value:
    #     points = int(points * 1.1)

    return points