from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.engine import DialogueEngine, Reply

router = Router()


def build_markup(reply: Reply) -> InlineKeyboardMarkup | None:
    if not reply.buttons:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in reply.buttons
            if row
        ]
    )


def attach_engine(engine: DialogueEngine) -> Router:
    @router.message(CommandStart())
    async def start(message: Message) -> None:
        reply = engine.handle(message.chat.id, text="/start")
        await message.answer(reply.text, reply_markup=build_markup(reply))

    @router.message(F.text)
    async def on_text(message: Message) -> None:
        reply = engine.handle(message.chat.id, text=message.text)
        await message.answer(reply.text, reply_markup=build_markup(reply))

    @router.callback_query()
    async def on_callback(query: CallbackQuery) -> None:
        await query.answer()
        chat_id = query.message.chat.id if query.message else query.from_user.id
        reply = engine.handle(chat_id, callback=query.data)
        if query.message:
            await query.message.answer(reply.text, reply_markup=build_markup(reply))
        else:
            await query.bot.send_message(chat_id, reply.text, reply_markup=build_markup(reply))

    return router
