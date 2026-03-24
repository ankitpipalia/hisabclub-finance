"""Seed data: top Indian merchants with matching patterns and default categories.

Format: (merchant_name, category_path, patterns)
- category_path: "Parent > Child" to match seeded categories
- patterns: list of (pattern, pattern_type) tuples
"""

MERCHANTS = [
    # ─── Food Delivery ───
    ("Swiggy", "Food & Dining > Food Delivery", [
        ("SWIGGY", "contains"),
        ("BUNDL TECHNOLOGIES", "contains"),
    ]),
    ("Zomato", "Food & Dining > Food Delivery", [
        ("ZOMATO", "contains"),
        ("ZOMAT", "contains"),
    ]),
    ("Blinkit", "Food & Dining > Groceries", [
        ("BLINKIT", "contains"),
        ("GROFERS", "contains"),
    ]),
    ("Zepto", "Food & Dining > Groceries", [
        ("ZEPTO", "contains"),
        ("KIRANAKART", "contains"),
    ]),
    ("BigBasket", "Food & Dining > Groceries", [
        ("BIGBASKET", "contains"),
        ("SUPERMARKET GROCERY", "contains"),
    ]),
    ("Dunzo", "Food & Dining > Groceries", [
        ("DUNZO", "contains"),
    ]),
    ("McDonald's", "Food & Dining > Restaurants", [
        ("MCDONALD", "contains"),
        ("MCD ", "contains"),
    ]),
    ("Domino's", "Food & Dining > Restaurants", [
        ("DOMINOS", "contains"),
        ("DOMINO", "contains"),
        ("JUBILANT FOOD", "contains"),
    ]),
    ("Starbucks", "Food & Dining > Cafe & Snacks", [
        ("STARBUCKS", "contains"),
    ]),

    # ─── Online Shopping ───
    ("Amazon India", "Shopping > Online Shopping", [
        ("AMAZON", "contains"),
        ("AMZN", "contains"),
        ("AMZ*", "contains"),
    ]),
    ("Flipkart", "Shopping > Online Shopping", [
        ("FLIPKART", "contains"),
        ("FKART", "contains"),
    ]),
    ("Myntra", "Shopping > Clothing & Fashion", [
        ("MYNTRA", "contains"),
    ]),
    ("Ajio", "Shopping > Clothing & Fashion", [
        ("AJIO", "contains"),
    ]),
    ("Nykaa", "Shopping > Clothing & Fashion", [
        ("NYKAA", "contains"),
    ]),
    ("Meesho", "Shopping > Online Shopping", [
        ("MEESHO", "contains"),
    ]),
    ("Croma", "Shopping > Electronics", [
        ("CROMA", "contains"),
    ]),

    # ─── Transport ───
    ("Uber", "Transport > Cab & Auto", [
        ("UBER", "contains"),
    ]),
    ("Ola", "Transport > Cab & Auto", [
        ("OLA ", "contains"),
        ("OLACABS", "contains"),
        ("ANI TECHNOLOGIES", "contains"),
    ]),
    ("Rapido", "Transport > Cab & Auto", [
        ("RAPIDO", "contains"),
    ]),
    ("Indian Oil (IOCL)", "Transport > Fuel", [
        ("INDIAN OIL", "contains"),
        ("IOCL", "contains"),
    ]),
    ("HP Petrol", "Transport > Fuel", [
        ("HP PETROL", "contains"),
        ("HPCL", "contains"),
        ("HINDUSTAN PETROLEUM", "contains"),
    ]),
    ("Bharat Petroleum", "Transport > Fuel", [
        ("BHARAT PETROLEUM", "contains"),
        ("BPCL", "contains"),
    ]),
    ("FASTag", "Transport > Parking & Toll", [
        ("FASTAG", "contains"),
        ("NHAI", "contains"),
        ("TOLL PLAZA", "contains"),
    ]),
    ("IRCTC", "Transport > Flight & Train", [
        ("IRCTC", "contains"),
    ]),
    ("MakeMyTrip", "Travel > Flights", [
        ("MAKEMYTRIP", "contains"),
        ("MMT", "contains"),
    ]),

    # ─── Bills & Utilities ───
    ("Jio", "Bills & Utilities > Mobile & Internet", [
        ("JIO ", "contains"),
        ("RELIANCE JIO", "contains"),
    ]),
    ("Airtel", "Bills & Utilities > Mobile & Internet", [
        ("AIRTEL", "contains"),
        ("BHARTI AIRTEL", "contains"),
    ]),
    ("Vi (Vodafone Idea)", "Bills & Utilities > Mobile & Internet", [
        ("VODAFONE", "contains"),
        ("VI ", "contains"),
    ]),
    ("Tata Play", "Bills & Utilities > DTH & Cable", [
        ("TATA PLAY", "contains"),
        ("TATA SKY", "contains"),
    ]),
    ("ACT Fibernet", "Bills & Utilities > Mobile & Internet", [
        ("ACT FIBERNET", "contains"),
        ("ATRIA CONVERGENCE", "contains"),
    ]),

    # ─── Entertainment / OTT ───
    ("Netflix", "Entertainment > OTT Subscriptions", [
        ("NETFLIX", "contains"),
    ]),
    ("Amazon Prime", "Entertainment > OTT Subscriptions", [
        ("PRIME VIDEO", "contains"),
        ("AMAZON PRIME", "contains"),
    ]),
    ("Hotstar", "Entertainment > OTT Subscriptions", [
        ("HOTSTAR", "contains"),
        ("DISNEY", "contains"),
    ]),
    ("Spotify", "Entertainment > OTT Subscriptions", [
        ("SPOTIFY", "contains"),
    ]),
    ("YouTube Premium", "Entertainment > OTT Subscriptions", [
        ("YOUTUBE", "contains"),
        ("GOOGLE *YouTube", "contains"),
    ]),
    ("Apple", "Entertainment > OTT Subscriptions", [
        ("APPLE.COM", "contains"),
        ("APPLE STORE", "contains"),
        ("ITUNES", "contains"),
    ]),
    ("Google Play", "Entertainment > OTT Subscriptions", [
        ("GOOGLE PLAY", "contains"),
        ("GOOGLE *", "contains"),
    ]),
    ("BookMyShow", "Entertainment > Movies & Events", [
        ("BOOKMYSHOW", "contains"),
        ("BMS ", "contains"),
    ]),
    ("PVR INOX", "Entertainment > Movies & Events", [
        ("PVR", "contains"),
        ("INOX", "contains"),
    ]),

    # ─── Health ───
    ("Apollo Pharmacy", "Health & Fitness > Medical & Pharmacy", [
        ("APOLLO", "contains"),
    ]),
    ("PharmEasy", "Health & Fitness > Medical & Pharmacy", [
        ("PHARMEASY", "contains"),
    ]),
    ("1mg", "Health & Fitness > Medical & Pharmacy", [
        ("1MG", "contains"),
        ("TATA 1MG", "contains"),
    ]),
    ("Cult.fit", "Health & Fitness > Gym & Sports", [
        ("CULT.FIT", "contains"),
        ("CULTFIT", "contains"),
        ("CUREFIT", "contains"),
    ]),

    # ─── Financial ───
    ("Groww", "Financial > Investment", [
        ("GROWW", "contains"),
    ]),
    ("Zerodha", "Financial > Investment", [
        ("ZERODHA", "contains"),
    ]),
    ("LIC", "Financial > Insurance", [
        ("LIC OF INDIA", "contains"),
        ("LIFE INSURANCE CORP", "contains"),
    ]),

    # ─── Government ───
    ("E-Challan", "Government > Challan & Fine", [
        ("ECHALLAN", "contains"),
        ("E-CHALLAN", "contains"),
        ("TRAFFIC FINE", "contains"),
    ]),

    # ─── Cash ───
    ("ATM Withdrawal", "Cash & ATM > ATM Withdrawal", [
        ("ATM WITHDRAWAL", "contains"),
        ("ATM WDL", "contains"),
        ("CASH WITHDRAWAL", "contains"),
        ("ATM-", "contains"),
    ]),
]
