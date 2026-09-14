"""Aggregate bot analytics; never store message bodies or photos."""
import logging
import os
from contextlib import closing

import db


def record_activity(user_id, name, photo=False, recommendation=False):
    db.save_user(user_id, name)
    with closing(db._connect()) as connection, connection:
        connection.execute("""
            INSERT INTO daily_activity
                (telegram_id, day, interactions, photo_requests, recommendation_requests)
            VALUES (?, date('now'), 1, ?, ?)
            ON CONFLICT(telegram_id, day) DO UPDATE SET
                interactions = interactions + 1,
                photo_requests = photo_requests + excluded.photo_requests,
                recommendation_requests = recommendation_requests + excluded.recommendation_requests
        """, (user_id, int(photo), int(recommendation)))


def get_stats():
    with closing(db._connect()) as connection:
        total, new = connection.execute("""
            SELECT COUNT(*), COALESCE(SUM(date(created_at) = date('now')), 0)
            FROM users
        """).fetchone()
        today, week, photos, recommendations = connection.execute("""
            SELECT COUNT(DISTINCT CASE WHEN day = date('now') THEN telegram_id END),
                   COUNT(DISTINCT CASE WHEN day >= date('now', '-6 days') THEN telegram_id END),
                   COALESCE(SUM(photo_requests), 0),
                   COALESCE(SUM(recommendation_requests), 0)
            FROM daily_activity
        """).fetchone()
    return dict(total=total, new=new, today=today, week=week,
                photos=photos, recommendations=recommendations)


async def track_activity(update, context):
    user = update.effective_user
    if not user or user.is_bot:
        return
    message = update.effective_message
    if not message:
        return
    command = (message.text or '').split(maxsplit=1)[0:1]
    command = command[0].split('@')[0].lower() if command else ''
    callback = update.callback_query.data if update.callback_query else None
    try:
        record_activity(user.id, user.first_name,
                        photo=bool(update.message and update.message.photo),
                        recommendation=command == '/recommend' or callback in ('start_recommend', 'similar'))
    except Exception:
        logging.getLogger(__name__).exception('Could not record bot activity')


async def myid_cmd(update, context):
    if update.effective_chat.type == 'private':
        await update.effective_message.reply_text(f'Your Telegram user ID: {update.effective_user.id}')


async def stats_cmd(update, context):
    admin_id = os.getenv('ADMIN_TELEGRAM_ID', '').strip()
    if (not admin_id or str(update.effective_user.id) != admin_id
            or update.effective_chat.type != 'private'):
        await update.effective_message.reply_text('This command is available only to the admin in private chat.')
        return
    stats = get_stats()
    await update.effective_message.reply_text(
        'WhatDaBook stats\n\n'
        f'Total saved users: {stats["total"]}\n'
        f'New users today: {stats["new"]}\n'
        f'Active today: {stats["today"]}\n'
        f'Active last 7 days: {stats["week"]}\n'
        f'Photo scans requested: {stats["photos"]}\n'
        f'Recommendations requested: {stats["recommendations"]}\n\n'
        'Days use UTC. Activity and request counts begin with this update. '
        'Requests include unsuccessful attempts.'
    )
