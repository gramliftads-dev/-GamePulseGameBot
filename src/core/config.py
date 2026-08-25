# test_config.py
from src.core.config import settings, print_settings, get_settings_dict

def test_settings():
    """Test settings loading"""
    # Test required fields
    assert settings.TELEGRAM_BOT_TOKEN is not None
    assert settings.POSTGRES_PASSWORD is not None
    assert settings.API_SECRET_KEY is not None
    
    # Test admin IDs parsing
    if settings.ADMIN_USER_IDS:
        assert isinstance(settings.admin_ids, list)
        assert all(isinstance(x, int) for x in settings.admin_ids)
    
    # Test database URL
    assert settings.DATABASE_URL.startswith("postgresql+asyncpg://")
    
    # Test Redis URL
    assert settings.REDIS_URL.startswith("redis://")
    
    # Test streak milestones
    assert isinstance(settings.STREAK_MILESTONE_BONUS, dict)
    assert 7 in settings.STREAK_MILESTONE_BONUS
    
    print("✅ All tests passed!")
    print_settings()

if __name__ == "__main__":
    test_settings()
