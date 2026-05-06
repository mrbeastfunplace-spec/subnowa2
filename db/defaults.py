from __future__ import annotations

from config import Settings
from db.base import ButtonActionType, Language, PaymentProviderType, ProductStatus


DEFAULT_CATEGORIES = [
    {
        "code": "saas",
        "slug": "saas-subscriptions",
        "sort_order": 10,
        "is_active": True,
        "translations": {
            Language.RU.value: {"name": "SaaS подписки", "description": "Цифровые подписки и сервисы."},
            Language.UZ.value: {"name": "SaaS obunalari", "description": "Raqamli obunalar va servislar."},
            Language.EN.value: {"name": "SaaS subscriptions", "description": "Digital subscriptions and services."},
        },
    },
    {
        "code": "game_values",
        "slug": "game-values",
        "sort_order": 20,
        "is_active": True,
        "translations": {
            Language.RU.value: {"name": "Игровые ценности", "description": "Игровые валюты и цифровые товары."},
            Language.UZ.value: {"name": "O'yin qiymatlari", "description": "O'yin valyutalari va raqamli mahsulotlar."},
            Language.EN.value: {"name": "Game values", "description": "Game currencies and digital goods."},
        },
    },
]


DEFAULT_PRODUCTS = [
    {
        "code": "chatgpt_plus_month",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "manual",
        "workflow_type": "chatgpt_manual",
        "price": "99000.00",
        "currency": "UZS",
        "sort_order": 10,
        "show_in_catalog": True,
        "extra_data": {"collect_gmail": True, "requires_subscription_check": True},
        "translations": {
            Language.RU.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "Подписка ChatGPT Plus/Pro.\n\nПосле оплаты заказ поступает админу на ручное выполнение.",
            },
            Language.UZ.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "ChatGPT Plus/Pro obunasi.\n\nTo'lovdan so'ng buyurtma administratorga qo'lda bajarish uchun yuboriladi.",
            },
            Language.EN.value: {
                "name": "ChatGPT Plus/Pro",
                "description": "ChatGPT Plus/Pro subscription.\n\nAfter payment the order goes to an admin for manual completion.",
            },
        },
    },
    {
        "code": "capcut_pro_month",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "auto",
        "workflow_type": "capcut_auto",
        "price": "49000.00",
        "currency": "UZS",
        "sort_order": 20,
        "show_in_catalog": True,
        "extra_data": {"stock_code": "capcut"},
        "translations": {
            Language.RU.value: {
                "name": "CapCut Pro",
                "description": "CapCut Pro на 1 месяц.\n\nПосле подтверждения оплаты бот автоматически выдаёт логин и пароль.",
            },
            Language.UZ.value: {
                "name": "CapCut Pro",
                "description": "1 oylik CapCut Pro.\n\nTo'lov tasdiqlangach bot login va parolni avtomatik beradi.",
            },
            Language.EN.value: {
                "name": "CapCut Pro",
                "description": "CapCut Pro for 1 month.\n\nAfter payment confirmation the bot automatically delivers login and password.",
            },
        },
    },
    {
        "code": "capcut_personal_month",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "manual",
        "workflow_type": "manual",
        "price": "79000.00",
        "currency": "UZS",
        "sort_order": 21,
        "show_in_catalog": False,
        "extra_data": {"variant": "capcut_personal"},
        "translations": {
            Language.RU.value: {
                "name": "CapCut Pro — Личный аккаунт",
                "description": "Личный аккаунт CapCut Pro на 30 дней.",
            },
            Language.UZ.value: {
                "name": "CapCut Pro — Shaxsiy akkaunt",
                "description": "30 kunlik shaxsiy CapCut Pro akkaunti.",
            },
            Language.EN.value: {
                "name": "CapCut Pro — Personal account",
                "description": "Personal CapCut Pro account for 30 days.",
            },
        },
    },
    {
        "code": "chatgpt_trial_3d",
        "category_code": "saas",
        "status": ProductStatus.ACTIVE.value,
        "delivery_type": "manual",
        "workflow_type": "trial",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 30,
        "show_in_catalog": False,
        "extra_data": {"requires_subscription_check": True, "trial_days": 3},
        "translations": {
            Language.RU.value: {"name": "ChatGPT Trial 3 дня", "description": "Пробная заявка ChatGPT на 3 дня после проверки администратором."},
            Language.UZ.value: {"name": "ChatGPT Trial 3 kun", "description": "Administrator tekshiruvdan keyin 3 kunlik ChatGPT sinov arizasi."},
            Language.EN.value: {"name": "ChatGPT Trial 3 days", "description": "3-day ChatGPT trial request after admin review."},
        },
    },
    {
        "code": "grok_template",
        "category_code": "saas",
        "status": ProductStatus.HIDDEN.value,
        "delivery_type": "manual",
        "workflow_type": "manual",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 40,
        "show_in_catalog": True,
        "extra_data": {},
        "translations": {
            Language.RU.value: {"name": "Grok", "description": "Шаблон товара Grok. Настройте цену и включите товар из админки."},
            Language.UZ.value: {"name": "Grok", "description": "Grok mahsuloti shabloni. Narxni sozlang va admin paneldan yoqing."},
            Language.EN.value: {"name": "Grok", "description": "Grok product template. Configure the price and enable it from the admin panel."},
        },
    },
    {
        "code": "adobe_template",
        "category_code": "saas",
        "status": ProductStatus.HIDDEN.value,
        "delivery_type": "manual",
        "workflow_type": "manual",
        "price": "0.00",
        "currency": "UZS",
        "sort_order": 50,
        "show_in_catalog": True,
        "extra_data": {},
        "translations": {
            Language.RU.value: {"name": "Adobe", "description": "Шаблон товара Adobe. Настройте цену и включите товар из админки."},
            Language.UZ.value: {"name": "Adobe", "description": "Adobe mahsuloti shabloni. Narxni sozlang va admin paneldan yoqing."},
            Language.EN.value: {"name": "Adobe", "description": "Adobe product template. Configure the price and enable it from the admin panel."},
        },
    },
]


DEFAULT_TEXTS = {
    "user.choose_language": {
        "group": "user",
        "description": "Prompt before language selection",
        "translations": {"ru": "Выберите язык", "uz": "Tilni tanlang", "en": "Choose language"},
    },
    "user.main_title": {
        "group": "user",
        "description": "Main menu title",
        "translations": {
            "ru": (
                "<tg-emoji emoji-id='5312016504939087914'>💮</tg-emoji> Добро пожаловать в\n"
                "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
                "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
                "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
                "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
                "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
                "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
                "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji>"
            ),
            "uz": (
                "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
                "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
                "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
                "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
                "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
                "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
                "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji> ga xush kelibsiz"
            ),
            "en": (
                "Welcome to "
                "<tg-emoji emoji-id='5332807088940785741'>S</tg-emoji>"
                "<tg-emoji emoji-id='5330069773139059849'>U</tg-emoji>"
                "<tg-emoji emoji-id='5330453760395191684'>B</tg-emoji>"
                "<tg-emoji emoji-id='5359736027080565026'>N</tg-emoji>"
                "<tg-emoji emoji-id='5361583176550457135'>O</tg-emoji>"
                "<tg-emoji emoji-id='5395613572531232916'>V</tg-emoji>"
                "<tg-emoji emoji-id='5226734466315067436'>A</tg-emoji>"
            ),
        },
    },
    "user.main_body": {
        "group": "user",
        "description": "Main menu body",
        "translations": {
            "ru": (
                "│ — удобный доступ к цифровым сервисам без лишних сложностей.\n\n"
                "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Здесь можно подключить:\n"
                "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
                "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
                "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
                "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe и другие сервисы\n\n"
                "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> Как всё происходит:\n"
                "— выбираете сервис\n"
                "— оформляете заявку\n"
                "— получаете доступ\n\n"
                "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> Мы остаёмся на связи и помогаем на каждом этапе.\n\n"
                "Почему выбирают нас?\n"
                "✅ Быстрое подключение\n"
                "✅ Проверенные решения\n"
                "✅ Поддержка 24/7\n\n"
                "<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Сайт</a>\n"
                "<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Отзывы</a>\n\n"
                "<tg-emoji emoji-id='5469778417045574463'>👇</tg-emoji> Выберите нужный раздел ниже <tg-emoji emoji-id='5469778417045574463'>👇</tg-emoji>"
            ),
            "uz": (
                "Raqamli xizmatlarga oddiy va qulay ulanish.\n\n"
                "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Bu yerda quyidagilar mavjud:\n"
                "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
                "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
                "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
                "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe va boshqa xizmatlar\n\n"
                "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> Qanday ishlaydi:\n"
                "— xizmatni tanlaysiz\n"
                "— buyurtma berasiz\n"
                "— kirish ma'lumotini olasiz\n\n"
                "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> Har bir bosqichda yordam beramiz.\n\n"
                "Nega bizni tanlashadi?\n"
                "✅ Tez ulanish\n"
                "✅ Ishonchli yechimlar\n"
                "✅ 24/7 qo'llab-quvvatlash\n\n"
                "<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Sayt</a>\n"
                "<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Fikrlar</a>\n\n"
                "👇 Quyidagi bo'limni tanlang 👇"
            ),
            "en": (
                "Seamless access to digital services without the hassle.\n\n"
                "<tg-emoji emoji-id='5407076281898512830'>🔥</tg-emoji> Available services:\n"
                "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT PLUS\n"
                "<tg-emoji emoji-id='5364339557712020484'>🎬</tg-emoji> CapCut PRO\n"
                "<tg-emoji emoji-id='5330337435500951363'>🚀</tg-emoji> Grok\n"
                "<tg-emoji emoji-id='5357394595594388140'>🎨</tg-emoji> Adobe and other services\n\n"
                "<tg-emoji emoji-id='5438176453621457379'>⚡</tg-emoji> How it works:\n"
                "— choose a service\n"
                "— place your order\n"
                "— get access\n\n"
                "<tg-emoji emoji-id='5447410659077661506'>💬</tg-emoji> We help you at every step.\n\n"
                "Why choose us?\n"
                "✅ Fast connection\n"
                "✅ Proven solutions\n"
                "✅ 24/7 support\n\n"
                "<tg-emoji emoji-id='5443038326535759644'>🌐</tg-emoji> <a href='{ABOUT_URL}'>Website</a>\n"
                "<tg-emoji emoji-id='5424972470023104089'>💬</tg-emoji> <a href='{REVIEW_URL}'>Reviews</a>\n\n"
                "👇 Choose a section below 👇"
            ),
        },
    },
    "user.catalog_title": {
        "group": "user",
        "description": "Catalog title",
        "translations": {"ru": "Выберите сервис", "uz": "Xizmatni tanlang", "en": "Choose a service"},
    },
    "user.profile_title": {
        "group": "user",
        "description": "Profile title",
        "translations": {"ru": "Ваш профиль\n\nВыберите раздел 👇", "uz": "Sizning profilingiz\n\nBo‘limni tanlang 👇", "en": "Your profile\n\nChoose a section 👇"},
    },
    "user.no_completed_orders": {
        "group": "user",
        "description": "No completed orders",
        "translations": {
            "ru": "У вас пока нет заказов.",
            "uz": "Sizda hali buyurtmalar yo‘q.",
            "en": "You have no orders yet.",
        },
    },
    "user.order_history_title": {
        "group": "user",
        "description": "History title",
        "translations": {"ru": "История заказов", "uz": "Buyurtmalar tarixi", "en": "Order history"},
    },
    "user.promo_enter": {
        "group": "user",
        "description": "Promo code prompt",
        "translations": {"ru": "Введите промокод.", "uz": "Promokodni kiriting.", "en": "Enter promo code."},
    },
    "user.promo_invalid": {
        "group": "user",
        "description": "Promo code invalid",
        "translations": {
            "ru": "К сожалению, такого промокода не существует.",
            "uz": "Afsuski, bunday promokod mavjud emas.",
            "en": "Sorry, this promo code does not exist.",
        },
    },
    "user.faq_title": {
        "group": "user",
        "description": "FAQ title",
        "translations": {"ru": "FAQ", "uz": "FAQ", "en": "FAQ"},
    },
    "user.faq_body": {
        "group": "user",
        "description": "FAQ body",
        "translations": {
            "ru": (
                "1. Что я получу после оплаты?\n"
                "Вы получите подтверждение заказа и дальнейшие инструкции по подключению.\n\n"
                "2. Как подключается ChatGPT Plus?\n"
                "Мы отправляем приглашение на ваш Gmail, после принятия подписка активируется.\n\n"
                "3. Как подключается CapCut Pro?\n"
                "После подтверждения оплаты вы получаете готовые данные для входа.\n\n"
                "4. Сколько времени занимает подключение?\n"
                "Обычно от нескольких минут до нескольких часов, в зависимости от очереди.\n\n"
                "5. Какие способы оплаты доступны?\n"
                "Click, Humo, Visa и USDT (TRC20).\n\n"
                "6. Нужен ли VPN для использования?\n"
                "В большинстве случаев нет.\n\n"
                "7. Можно ли заказать несколько аккаунтов?\n"
                "Да, используйте кнопку «Хочу несколько», и администратор обработает заявку.\n\n"
                "8. Что делать, если письмо не пришло?\n"
                "Проверьте папки «Спам» и «Промоакции», затем напишите в поддержку.\n\n"
                "9. Можно ли заказать другой сервис?\n"
                "Да, в разделе «Другое» можно оставить заявку на нужную подписку.\n\n"
                "10. Что делать, если возникла проблема после покупки?\n"
                "Напишите в поддержку, указав номер заказа и суть проблемы."
            ),
            "uz": (
                "1. To‘lovdan keyin nima olaman?\n"
                "Buyurtma tasdig‘i va ulash bo‘yicha ko‘rsatmalar olasiz.\n\n"
                "2. ChatGPT Plus qanday ulanadi?\n"
                "Gmail'ingizga yuborilgan havolani tasdiqlaysiz va obuna faollashadi.\n\n"
                "3. CapCut Pro qanday beriladi?\n"
                "To‘lov tasdiqlangach, tayyor login va parol yuboriladi.\n\n"
                "4. Ulanish qancha vaqt oladi?\n"
                "Odatda bir necha daqiqadan bir necha soatgacha.\n\n"
                "5. Qanday to‘lov usullari mavjud?\n"
                "Click, Humo, Visa va USDT (TRC20).\n\n"
                "6. VPN kerakmi?\n"
                "Ko‘p hollarda yo‘q.\n\n"
                "7. Bir nechta akkaunt buyurtma qilish mumkinmi?\n"
                "Ha, «Bir nechta kerak» tugmasi orqali so‘rov yuboring.\n\n"
                "8. Xat kelmasa nima qilaman?\n"
                "Spam va Promotions papkalarini tekshiring, keyin yordamga yozing.\n\n"
                "9. Boshqa xizmat buyurtma qilish mumkinmi?\n"
                "Ha, «Boshqa» bo‘limida so‘rov qoldiring.\n\n"
                "10. Xariddan keyin muammo bo‘lsa nima qilaman?\n"
                "Buyurtma raqami bilan yordam xizmatiga yozing."
            ),
            "en": (
                "1. What do I receive after payment?\n"
                "You receive order confirmation and connection instructions.\n\n"
                "2. How is ChatGPT Plus activated?\n"
                "We send an invitation to your Gmail and the subscription activates after you accept it.\n\n"
                "3. How is CapCut Pro delivered?\n"
                "After payment confirmation you receive ready-to-use login details.\n\n"
                "4. How long does activation take?\n"
                "Usually from a few minutes to a few hours.\n\n"
                "5. Which payment methods are available?\n"
                "Click, Humo, Visa, and USDT (TRC20).\n\n"
                "6. Do I need a VPN?\n"
                "Usually no.\n\n"
                "7. Can I order several accounts?\n"
                "Yes, use the several-accounts button and the admin will process it.\n\n"
                "8. What if the email does not arrive?\n"
                "Check Spam and Promotions, then contact support.\n\n"
                "9. Can I request another service?\n"
                "Yes, use the Other section and send your request.\n\n"
                "10. What should I do if there is a problem after purchase?\n"
                "Contact support and include your order number."
            ),
        },
    },
    "user.choose_payment_method": {
        "group": "user",
        "description": "Choose payment method text",
        "translations": {"ru": "Выберите способ оплаты.", "uz": "To'lov usulini tanlang.", "en": "Choose a payment method."},
    },
    "user.send_payment_proof": {
        "group": "user",
        "description": "Prompt to send check",
        "translations": {
            "ru": "После оплаты отправьте чек фото или документом.",
            "uz": "To'lovdan so'ng chekni rasm yoki hujjat sifatida yuboring.",
            "en": "After payment send the receipt as a photo or document.",
        },
    },
    "user.payment_check_saved": {
        "group": "user",
        "description": "Check uploaded",
        "translations": {
            "ru": "Чек получен. Ожидайте проверки администратора.",
            "uz": "Chek qabul qilindi. Administrator tekshiruvini kuting.",
            "en": "Receipt received. Please wait for admin review.",
        },
    },
    "user.payment_rejected": {
        "group": "user",
        "description": "Payment rejected message",
        "translations": {
            "ru": "Ваша оплата отклонена.\n\nПроверьте чек или свяжитесь с техподдержкой.",
            "uz": "To‘lovingiz rad etildi.\n\nChekni tekshiring yoki yordam xizmatiga murojaat qiling.",
            "en": "Your payment was rejected.\n\nPlease check your receipt or contact support.",
        },
    },
    "user.payment_approved": {
        "group": "user",
        "description": "Payment approved",
        "translations": {"ru": "Оплата подтверждена.", "uz": "To'lov tasdiqlandi.", "en": "Payment confirmed."},
    },
    "user.order_processing": {
        "group": "user",
        "description": "Order processing",
        "translations": {"ru": "Ваш заказ передан в обработку.", "uz": "Buyurtmangiz ishlovga o'tkazildi.", "en": "Your order is now being processed."},
    },
    "user.order_completed": {
        "group": "user",
        "description": "Order completed",
        "translations": {"ru": "Заказ завершён.", "uz": "Buyurtma yakunlandi.", "en": "Order completed."},
    },
    "user.order_cancelled": {
        "group": "user",
        "description": "Order cancelled",
        "translations": {
            "ru": "Заказ {order_number}\nСтатус: отменён\nСообщение: заказ отменён",
            "uz": "Buyurtma {order_number}\nHolat: bekor qilindi\nXabar: buyurtma bekor qilindi",
            "en": "Order {order_number}\nStatus: cancelled\nMessage: order cancelled",
        },
    },
    "user.stock_empty": {
        "group": "user",
        "description": "Stock empty message",
        "translations": {
            "ru": "В данный момент товар закончился.\n\nПожалуйста, попробуйте позже или свяжитесь с поддержкой.",
            "uz": "Hozirda mahsulot tugagan.\n\nIltimos, keyinroq urinib ko‘ring yoki yordamga yozing.",
            "en": "This item is currently out of stock.\n\nPlease try again later or contact support.",
        },
    },
    "user.trial_gmail_prompt": {
        "group": "user",
        "description": "Trial Gmail prompt",
        "translations": {"ru": "Введите Gmail для подключения ChatGPT.", "uz": "ChatGPT uchun Gmail kiriting.", "en": "Enter your Gmail for ChatGPT activation."},
    },
    "user.invalid_gmail": {
        "group": "user",
        "description": "Invalid Gmail input",
        "translations": {
            "ru": "Введите корректный Gmail в формате name@gmail.com.",
            "uz": "Gmailni name@gmail.com formatida to‘g‘ri kiriting.",
            "en": "Enter a valid Gmail in the format name@gmail.com.",
        },
    },
    "user.trial_subscribe": {
        "group": "user",
        "description": "Subscribe before trial",
        "translations": {"ru": "Подпишитесь на канал и нажмите кнопку проверки.", "uz": "Kanalga obuna bo'ling va tekshirish tugmasini bosing.", "en": "Subscribe to the channel and press the check button."},
    },
    "user.trial_not_subscribed": {
        "group": "user",
        "description": "Trial not subscribed",
        "translations": {"ru": "Вы ещё не подписались на канал.", "uz": "Siz hali kanalga obuna bo'lmadingiz.", "en": "You are not subscribed to the channel yet."},
    },
    "user.trial_already_used": {
        "group": "user",
        "description": "Trial already used",
        "translations": {"ru": "Вы уже использовали пробную подписку.", "uz": "Siz sinov obunasidan allaqachon foydalangansiz.", "en": "You have already used the trial subscription."},
    },
    "user.trial_created": {
        "group": "user",
        "description": "Trial created",
        "translations": {
            "ru": "Заказ: {order_number}\nТовар: ChatGPT PLUS (3 дня)\nСтоимость: БЕСПЛАТНО\nСтатус: заказ в обработке",
            "uz": "Buyurtma: {order_number}\nMahsulot: ChatGPT PLUS (3 kun)\nNarx: BEPUL\nHolat: buyurtma ko‘rib chiqilmoqda",
            "en": "Order: {order_number}\nProduct: ChatGPT PLUS (3 days)\nPrice: FREE\nStatus: order is under review",
        },
    },
    "user.trial_approved": {
        "group": "user",
        "description": "Trial approved",
        "translations": {
            "ru": (
                "✅ Ваш заказ подтверждён.\n\n"
                "Заказ: {order_number}\n"
                "Товар: ChatGPT PLUS (3 дня)\n"
                "Стоимость: БЕСПЛАТНО\n"
                "Срок доступа: 3 дня\n\n"
                "<blockquote>Что будет дальше:\n"
                "1. Мы отправим приглашение на указанный Gmail.\n"
                "2. Вам нужно открыть письмо и подтвердить подключение.\n"
                "3. После подтверждения Plus активируется автоматически.</blockquote>\n\n"
                "Проверьте папки «Входящие» и «Спам». Если письмо не пришло, напишите в поддержку."
            ),
            "uz": (
                "✅ Buyurtmangiz tasdiqlandi.\n\n"
                "Buyurtma: {order_number}\n"
                "Mahsulot: ChatGPT PLUS (3 kun)\n"
                "Narx: BEPUL\n"
                "Muddat: 3 kun\n\n"
                "Havola emailingizga yuboriladi. Xatni ochib tasdiqlaganingizdan keyin 3 kunlik Plus faollashadi."
            ),
            "en": (
                "✅ Your order has been approved.\n\n"
                "Order: {order_number}\n"
                "Product: ChatGPT PLUS (3 days)\n"
                "Price: FREE\n"
                "Access period: 3 days\n\n"
                "We will send an invitation to your Gmail. Open the email and accept it to activate Plus."
            ),
        },
    },
    "user.trial_rejected": {
        "group": "user",
        "description": "Trial rejected",
        "translations": {
            "ru": "Пробные подписки закончились. Пожалуйста, выберите другой тип подписки.",
            "uz": "Sinov obunalari tugagan. Iltimos, boshqa turdagi obunani tanlang.",
            "en": "Trial subscriptions are out of stock. Please choose another subscription.",
        },
    },
    "user.chatgpt_gmail_prompt": {
        "group": "user",
        "description": "ChatGPT Gmail prompt",
        "translations": {"ru": "Введите Gmail, на который нужно подключить ChatGPT Plus.", "uz": "ChatGPT Plus ulash uchun Gmail kiriting.", "en": "Enter your Gmail for ChatGPT Plus activation."},
    },
    "user.chatgpt_saved_gmail_choice": {
        "group": "user",
        "description": "Saved Gmail prompt",
        "translations": {
            "ru": "Мы нашли Gmail, который вы уже использовали для ChatGPT:\n\n<b>{gmail}</b>\n\nОформить подписку на этот Gmail или указать другой?",
            "uz": "Siz ilgari ChatGPT uchun ishlatgan Gmail topildi:\n\n<b>{gmail}</b>\n\nObunani shu Gmailga rasmiylashtiraylikmi yoki boshqasini kiritasizmi?",
            "en": "We found a Gmail you already used for ChatGPT:\n\n<b>{gmail}</b>\n\nDo you want to use this Gmail or enter another one?",
        },
    },
    "user.custom_request_prompt": {
        "group": "user",
        "description": "Custom request prompt",
        "translations": {"ru": "Какую подписку вы хотели бы ещё получить дешевле?", "uz": "Qaysi obunani arzonroq olishni xohlaysiz?", "en": "Which subscription would you like to get cheaper?"},
    },
    "user.custom_request_created": {
        "group": "user",
        "description": "Custom request created",
        "translations": {
            "ru": "✅ Ваша заявка принята.\n\nАдминистратор увидит ваш запрос и свяжется с вами при необходимости.",
            "uz": "✅ So‘rovingiz qabul qilindi.\n\nAdministrator uni ko‘rib chiqadi va kerak bo‘lsa bog‘lanadi.",
            "en": "✅ Your request has been accepted.\n\nThe admin will review it and contact you if needed.",
        },
    },
    "button.back": {
        "group": "button",
        "description": "Back button",
        "translations": {"ru": "◀ Назад", "uz": "◀ Orqaga", "en": "◀ Back"},
    },
    "button.menu": {
        "group": "button",
        "description": "Main menu button",
        "translations": {"ru": "🏠 Меню", "uz": "🏠 Menyu", "en": "🏠 Menu"},
    },
    "button.buy": {
        "group": "button",
        "description": "Buy button",
        "translations": {"ru": "Оформить", "uz": "Rasmiylashtirish", "en": "Proceed"},
    },
    "button.history": {
        "group": "button",
        "description": "History button",
        "translations": {"ru": "📜 История заказов", "uz": "📜 Buyurtmalar tarixi", "en": "📜 Order history"},
    },
    "button.send_check": {
        "group": "button",
        "description": "Send check button",
        "translations": {"ru": "Отправить чек", "uz": "Chek yuborish", "en": "Send receipt"},
    },
    "button.check_subscription": {
        "group": "button",
        "description": "Check subscription button",
        "translations": {"ru": "Проверить подписку", "uz": "Obunani tekshirish", "en": "Check subscription"},
    },
    "button.use_saved_gmail": {
        "group": "button",
        "description": "Use saved gmail button",
        "translations": {"ru": "На этот", "uz": "Shu Gmail", "en": "Use this"},
    },
    "button.use_other_gmail": {
        "group": "button",
        "description": "Use other gmail button",
        "translations": {"ru": "Другой", "uz": "Boshqa", "en": "Other"},
    },
    "admin.panel_title": {
        "group": "admin",
        "description": "Admin main title",
        "translations": {"ru": "Админ-панель"},
    },
    "admin.stats_title": {
        "group": "admin",
        "description": "Stats title",
        "translations": {"ru": "Статистика"},
    },
    "admin.orders_title": {
        "group": "admin",
        "description": "Orders title",
        "translations": {"ru": "Заказы"},
    },
    "admin.products_title": {
        "group": "admin",
        "description": "Products title",
        "translations": {"ru": "Товары"},
    },
    "admin.payments_title": {
        "group": "admin",
        "description": "Payments title",
        "translations": {"ru": "Оплаты"},
    },
    "admin.stock_title": {
        "group": "admin",
        "description": "Stock title",
        "translations": {"ru": "Склад CapCut"},
    },
    "admin.buttons_title": {
        "group": "admin",
        "description": "Buttons title",
        "translations": {"ru": "Кнопки"},
    },
    "admin.texts_title": {
        "group": "admin",
        "description": "Texts title",
        "translations": {"ru": "Тексты"},
    },
}


DEFAULT_LAYOUTS = [
    {
        "code": "main_menu",
        "title": "Main menu",
        "scope": "user",
        "buttons": [
            {"code": "catalog", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:catalog", "style": "default", "row_index": 0, "sort_order": 10, "translations": {"ru": "💎 Подписки / тарифы", "uz": "💎 Obunalar / tariflar", "en": "💎 Subscriptions / Tariffs"}},
            {"code": "profile", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:profile", "style": "default", "row_index": 1, "sort_order": 10, "translations": {"ru": "👤 Профиль", "uz": "👤 Profil", "en": "👤 Profile"}},
            {"code": "languages", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:languages", "style": "default", "row_index": 1, "sort_order": 20, "translations": {"ru": "🌐 Языки", "uz": "🌐 Tillar", "en": "🌐 Languages"}},
            {"code": "support", "action_type": ButtonActionType.URL.value, "action_value": "__SUPPORT_URL__", "style": "default", "row_index": 2, "sort_order": 10, "translations": {"ru": "💬 Задать вопрос", "uz": "💬 Savol berish", "en": "💬 Support"}},
            {"code": "admin_profile", "action_type": ButtonActionType.URL.value, "action_value": "https://t.me/subnowa", "style": "default", "row_index": 2, "sort_order": 20, "translations": {"ru": "ADMIN", "uz": "ADMIN", "en": "ADMIN"}},
            {"code": "about", "action_type": ButtonActionType.URL.value, "action_value": "__ABOUT_URL__", "style": "default", "row_index": 3, "sort_order": 10, "translations": {"ru": "ℹ️ О нас", "uz": "ℹ️ Biz haqimizda", "en": "ℹ️ About us"}},
            {"code": "faq", "action_type": ButtonActionType.CALLBACK.value, "action_value": "menu:faq", "style": "default", "row_index": 3, "sort_order": 20, "translations": {"ru": "❓ FAQ", "uz": "❓ FAQ", "en": "❓ FAQ"}},
        ],
    },
    {
        "code": "admin_main",
        "title": "Admin main",
        "scope": "admin",
        "buttons": [
            {"code": "products", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:products", "style": "default", "row_index": 0, "sort_order": 10, "translations": {"ru": "Товары"}},
            {"code": "texts", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:texts", "style": "default", "row_index": 0, "sort_order": 20, "translations": {"ru": "Тексты"}},
            {"code": "buttons", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:buttons", "style": "default", "row_index": 1, "sort_order": 10, "translations": {"ru": "Кнопки"}},
            {"code": "payments", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:payments", "style": "default", "row_index": 1, "sort_order": 20, "translations": {"ru": "Оплаты"}},
            {"code": "stock", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:stock", "style": "default", "row_index": 2, "sort_order": 10, "translations": {"ru": "Склад CapCut"}},
            {"code": "orders", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:orders", "style": "default", "row_index": 2, "sort_order": 20, "translations": {"ru": "Заказы"}},
            {"code": "stats", "action_type": ButtonActionType.CALLBACK.value, "action_value": "admin:stats", "style": "default", "row_index": 3, "sort_order": 10, "translations": {"ru": "Статистика"}},
        ],
    },
]


def get_default_settings(settings: Settings) -> list[dict[str, str]]:
    return [
        {"key": "support_url", "value": settings.support_url, "value_type": "string", "description": "Support URL"},
        {"key": "about_url", "value": settings.about_url, "value_type": "string", "description": "About URL"},
        {"key": "review_url", "value": settings.review_url, "value_type": "string", "description": "Review URL"},
        {"key": "required_channel", "value": settings.required_channel, "value_type": "string", "description": "Channel required for ChatGPT trial/orders"},
    ]


def get_default_payment_methods() -> list[dict[str, object]]:
    return [
        {
            "code": "click",
            "provider_type": PaymentProviderType.CLICK.value,
            "admin_title": "Click",
            "credentials": "+998",
            "sort_order": 10,
            "translations": {
                "ru": {"title": "Click", "instructions": "Оплатите через Click на номер:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "Click", "instructions": "Click orqali quyidagi raqamga to'lang:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "Click", "instructions": "Pay via Click to this number:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
        {
            "code": "card",
            "provider_type": PaymentProviderType.CARD.value,
            "admin_title": "Humo/Visa",
            "credentials": "9860100126034816",
            "sort_order": 20,
            "translations": {
                "ru": {"title": "Humo / Visa", "instructions": "Переведите оплату на карту:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "Humo / Visa", "instructions": "To'lovni kartaga o'tkazing:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "Humo / Visa", "instructions": "Transfer the payment to this card:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
        {
            "code": "usdt_trc20",
            "provider_type": PaymentProviderType.CRYPTO.value,
            "admin_title": "USDT TRC20",
            "credentials": "TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs",
            "sort_order": 30,
            "translations": {
                "ru": {"title": "USDT TRC20", "instructions": "Переведите USDT TRC20 на адрес:\n<code>{credentials}</code>\n\nПосле оплаты отправьте чек."},
                "uz": {"title": "USDT TRC20", "instructions": "USDT TRC20 ni quyidagi manzilga o'tkazing:\n<code>{credentials}</code>\n\nTo'lovdan so'ng chek yuboring."},
                "en": {"title": "USDT TRC20", "instructions": "Transfer USDT TRC20 to this address:\n<code>{credentials}</code>\n\nSend the receipt after payment."},
            },
        },
    ]
