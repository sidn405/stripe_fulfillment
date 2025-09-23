# Map your Stripe IDs to the file you want to deliver.
# Prefer using PRICE IDs (price_...) from Stripe Checkout.
# You can also use product IDs (prod_...) if that’s how your site is set.
# Fill these with YOUR real IDs and file locations.

PRODUCTS = {
    # 5,000 Fitness Leads ($897)  — use the exact Price AND Product IDs
    "price_1S9EZ5QIY3HkFeeoDGjQrPVO": {
        "name": "5,000 Fitness Leads ($897)",
        "direct_link": "https://drive.google.com/file/d/155XlcLR3taTKY8sekHGCvOFv33HfyrmC/view?usp=drive_link",
    },
    "prod_T5PNHwQW1riHdR": {
        "name": "5,000 Fitness Leads ($897)",
        "direct_link": "https://drive.google.com/file/d/155XlcLR3taTKY8sekHGCvOFv33HfyrmC/view?usp=drive_link",
    },

    # 2,000 Fitness Leads ($297)
    "price_1S9Ei2QIY3HkFeeovCq24aWs": {
        "name": "2,000 Fitness Leads ($297)",
        "direct_link": "https://drive.google.com/file/d/1skfZHzMlMvFb26rbxYwLR3Ho6_VTH3MR/view?usp=drive_link",
    },
    "prod_T5PX9bhtOQwV9c": {
        "name": "2,000 Fitness Leads ($297)",
        "direct_link": "https://drive.google.com/file/d/1skfZHzMlMvFb26rbxYwLR3Ho6_VTH3MR/view?usp=drive_link",
    },

    # 500 Fitness Leads ($97)
    "price_1S9EkBQIY3HkFeeoB0OMwMCc": {
        "name": "500 Fitness Leads ($97)",
        "direct_link": "https://drive.google.com/file/d/1v4pYpTrAwlXjT2-G-UnZT6uiJjreRC7S/view?usp=drive_link",
    },
    "prod_T5PZa0TLWAxy1Z": {
        "name": "500 Fitness Leads ($97)",
        "direct_link": "https://drive.google.com/file/d/1v4pYpTrAwlXjT2-G-UnZT6uiJjreRC7S/view?usp=drive_link",
    },
}


ATTACHMENT_SIZE_LIMIT = 18 * 1024 * 1024  # 18MB

