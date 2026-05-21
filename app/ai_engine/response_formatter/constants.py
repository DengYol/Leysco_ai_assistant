"""Template constants for Response Formatter"""

OPENERS = {
    "GET_ITEM_PRICE": {
        "en": [
            "Sure! Let me check the price for you... 🔍",
            "Here's what I found:",
            "I've looked up the price:",
            "Let me get that information for you:",
            "Got it! Here's the pricing info:",
            "I found the price you're looking for:",
            "Here you go:"
        ],
        "sw": [
            "Sawa! Naangalia bei kwa ajili yako... 🔍",
            "Hiki ndio nilichopata:",
            "Nimeangalia bei:",
            "Nakupa taarifa hiyo:",
            "Subiri kidogo nitaangalia bei... 💰"
        ]
    },
    "GET_TOP_SELLING_ITEMS": {
        "en": [
            "Here are our hottest selling items right now! 🔥",
            "Customers are loving these products:",
            "Based on recent sales, these are the top performers:",
            "Here's what's flying off the shelves: 📦",
            "These are the bestsellers this period:",
            "The market is loving these products:",
            "Here's what's popular right now:"
        ],
        "sw": [
            "Hizi ndizo bidhaa zinazouzwa sana kwa sasa! 🔥",
            "Wateja wanapenda bidhaa hizi:",
            "Kulingana na mauzo ya hivi karibuni, hizi ndizo zinazoongoza:",
            "Hivi ndivyo vinavyouzwa kwa kasi: 📦"
        ]
    },
    "GET_SLOW_MOVING_ITEMS": {
        "en": [
            "Here are some items that need a bit of attention: 👀",
            "These products could use some marketing love:",
            "Based on turnover rates, consider promoting these:",
            "These items might benefit from a discount or bundle: 💡",
            "Here are some products that could use a boost:"
        ],
        "sw": [
            "Hizi ni bidhaa zinazohitaji uangalizi kidogo: 👀",
            "Bidhaa hizi zinahitaji uuzaji zaidi:",
            "Bidhaa hizi zinaweza kufaidika na punguzo au kifurushi: 💡"
        ]
    },
    "GET_ITEM_UNPRICED": {
        "en": [
            "I found the item, but I couldn't find a price for it. 🤔",
            "The item exists in our system, but no price is configured yet.",
            "I've located the product, but the price information is missing.",
        ],
        "sw": [
            "Nimeipata bidhaa, lakini bei yake haijasanidiwa bado. 🤔",
            "Bidhaa ipo kwenye mfumo, lakini bei haijapatikana."
        ]
    },
    "GET_ITEM_NOT_FOUND": {
        "en": [
            "I couldn't find that item. 🔍",
            "Sorry, I don't have that product in my catalog.",
            "I've searched but couldn't find that item.",
        ],
        "sw": [
            "Sikuweza kupata bidhaa hiyo. 🔍",
            "Samahani, sina bidhaa hiyo kwenye orodha yangu."
        ]
    }
}

CLOSERS = {
    "en": [
        "\n\n💡 Need anything else? I'm here to help! 😊",
        "\n\nIs there anything else you'd like to know?",
        "\n\nLet me know if you need more information!",
        "\n\nWhat else can I assist you with today?",
        "\n\nFeel free to ask about prices, stock, or customers!",
        "\n\nHappy to help with anything else!",
        "\n\nWould you like to check something else?",
        "\n\nI'm always here if you have more questions!",
        "\n\nCan I help you with anything else today?"
    ],
    "sw": [
        "\n\n💡 Unahitaji kitu kingine? Niko hapa kusaidia! 😊",
        "\n\nKuna chochote kingine ungependa kujua?",
        "\n\nNijulishe kama unahitaji maelezo zaidi!",
        "\n\nNini kingine ninachoweza kukusaidia nalo leo?"
    ]
}

NO_RESULTS = {
    "GET_ITEM_PRICE": {
        "en": "Hmm, I couldn't find any price information for that item. 🤔\n\n💡 Try:\n• Checking the spelling\n• Asking for a different product\n• Saying 'show me items' to browse our catalog\n• Using a shorter name (e.g., 'vegimax' instead of 'vegimax 30ml')",
        "sw": "Hmm, sikuweza kupata taarifa za bei kwa bidhaa hiyo. 🤔\n\n💡 Jaribu:\n• Angalia tahajia\n• Uliza kuhusu bidhaa nyingine"
    },
    "GET_TOP_SELLING_ITEMS": {
        "en": "I don't have enough sales data yet to show top selling items. 📊\n\n💡 Try asking for a specific product price or check back later for more sales data!",
        "sw": "Sina data ya kutosha ya mauzo bado. 📊"
    },
    "GET_SLOW_MOVING_ITEMS": {
        "en": "Great news! No slow moving items found - your inventory is moving well! 🎉\n\n💡 Your stock turnover looks healthy. Keep up the good work!",
        "sw": "Habari njema! Hakuna bidhaa zinazotembea polepole - hisa zako zinasonga vizuri! 🎉"
    },
    "GET_CUSTOMER_ORDERS": {
        "en": "I couldn't find any orders for this customer. 📋\n\n💡 Try:\n• Checking the customer name spelling\n• Creating a quotation first\n• Asking for a different customer",
        "sw": "Sikuweza kupata oda zozote kwa mteja huyu. 📋"
    },
    "GET_OUTSTANDING_DELIVERIES": {
        "en": "✅ No outstanding deliveries found! All deliveries are complete. 🎉\n\n💡 You're all caught up with deliveries!",
        "sw": "✅ Hakuna usafirishaji uliobaki! Usafirishaji wote umekamilika. 🎉"
    }
}

TIPS = {
    "GET_ITEM_PRICE": {
        "en": "\n\n💡 Tip: Ask 'price for [customer name]' to see customer-specific pricing!",
        "sw": "\n\n💡 Kidokezo: Uliza 'bei kwa [jina la mteja]' kuona bei maalum kwa mteja!"
    },
    "GET_TOP_SELLING_ITEMS": {
        "en": "\n\n💡 Tip: Want to check stock? Ask 'check stock for [item name]'",
        "sw": "\n\n💡 Kidokezo: Unataka kuangalia hisa? Uliza 'angalia hisa za [jina la bidhaa]'"
    },
    "GET_SLOW_MOVING_ITEMS": {
        "en": "\n\n💡 Tip: Consider running promotions or bundling slow movers with popular items!",
        "sw": "\n\n💡 Kidokezo: Fikiria kufanya promo au kufungasha bidhaa zinazotembea polepole!"
    },
    "GET_OUTSTANDING_DELIVERIES": {
        "en": "\n\n💡 Tip: Say 'create delivery note' to process these deliveries!",
        "sw": "\n\n💡 Kidokezo: Sema 'tengeneza hati ya usafirishaji' kusafirisha bidhaa hizi!"
    }
}