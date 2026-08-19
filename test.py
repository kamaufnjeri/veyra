from core.subtitle_translator import SubtitlesTranslator




def error_callback(error):
    print("\nERROR:")
    print(error)


def progress_callback(message, percentage):
    print(
        f"[{percentage:3d}%] {message}"
    )


translator = SubtitlesTranslator(
    source_language="es",
    target_language="en",




    batch_size=16,

    error_messages_callback=error_callback,
    progress_callback=progress_callback,
)




if not translator.is_available:
    raise SystemExit(
        "NLLB failed to initialize."
    )


tests = [
    "Hola, ¿cómo estás?",
    "Estoy bien.",
    "Buenos días.",
    "Me llamo Florence.",
]


for text in tests:

    result = translator.translate(text)

    print()
    print("SOURCE:")
    print(text)

    print("TARGET:")
    print(result)