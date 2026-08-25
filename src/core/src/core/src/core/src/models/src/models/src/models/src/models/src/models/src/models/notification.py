# Get unread notifications
unread = await session.query(Notification).filter(
    Notification.user_id == user.id,
    Notification.is_read == False,
    Notification.status == NotificationStatus.DELIVERED.value
).order_by(desc(Notification.created_at)).all()

# Get recent notifications (last 7 days)
recent = await session.query(Notification).filter(
    Notification.user_id == user.id,
    Notification.created_at >= datetime.utcnow() - timedelta(days=7)
).all()

# Get high priority notifications
high_priority = await session.query(Notification).filter(
    Notification.user_id == user.id,
    Notification.priority == NotificationPriority.HIGH.value,
    Notification.is
