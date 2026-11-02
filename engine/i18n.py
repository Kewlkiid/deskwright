"""The languages Deskwright speaks: English, Spanish, French, German, Portuguese and Chinese.

One table per language: what the models are told to answer in, the voice that talks back (a Meta MMS-TTS checkpoint;
Chinese has none, so the Mac's own voice), the speech locale for on-device listening, the spoken lines the narrator
uses, and the words of the voice commands. The app's own text is translated in the renderer (app/src/lib/i18n.ts).
"""
from __future__ import annotations

from .config import config

LANGUAGES: dict[str, dict] = {
    "en": {
        "name": "English",
        "tts_model": "facebook/mms-tts-eng",
        "say_voice": "",
        "locale": "en-US",
        "num_lang": "en",
        "lines": {
            "dictation_hint": "",
            "yes": "Yes?",
            "clicking": "Clicking", "double_clicking": "Double-clicking", "right_clicking": "Right-clicking",
            "typing_into": "Typing into", "pointing_at": "Pointing at", "dragging": "Dragging",
            "opening": "Opening {0}", "fixing": "Something changed. Fixing it.", "known_way": "I've seen this before. Going back.",
            "approval": "I need your approval. {0}", "this_step": "this step", "or": "or",
            "recording": "Recording. Show me the task.", "got_it": "Got it. Working out the steps.",
            "done": "Done. {0}", "stopped": "Stopped.", "declined": "Okay, I won't do that.",
            "failed": "I couldn't finish that. {0}",
        },
        "commands": {
            "approve": (r"approve|approved|i approve|approve it|approve that|yes|yeah|yep|yup|sure|ok(?:ay)?(?: do it)?|"
                        r"do it|go ahead|go for it|allow(?: it)?|accept(?: it)?|confirm(?:ed)?|yes please|yes do it|"
                        r"sounds good"),
            "decline": (r"(?:decline|declined|deny|denied|reject)(?: it| that)?|no|nope|don'?t|do not|don'?t do it|"
                        r"never ?mind|no thanks"),
            "send": (r"sen[dt](?: it| that| the message| message)?|submit(?: it| that)?|hit (?:send|enter)|"
                     r"press (?:send|enter)|post it|enter|go"),
            "stop": (r"stop|stop it|stop that|stop stop|halt|abort|cancel|cancel (?:it|that|the task)|stop the task|"
                     r"stop everything"),
            "hush": r"stop talking|be quiet|quiet|shush|shut up|silence|hush|enough|stop speaking",
            "close": r"send|send it|submit|done|over|enter|that's it|that is it",
            "input": r"(?:enter|task|type)\W+input|input",
            "teach": r"teach(?:\W+mode)?|let\W+me\W+teach\W+you",
            "teach_stop": r"(?:i'?m\W+|i\W+am\W+|we'?re\W+)?(?:done|finish(?:ed)?|stop(?:ped)?)\W+(?:teaching|recording)",
            "teach_cancel": r"cancel\W+(?:teaching|recording|the\W+demo(?:nstration)?)",
            "save": r"save(?:\W+(?:it|that|this))?(?:\W+(?:the\W+)?task|\W+as\W+a\W+task)?",
            "listen_off": r"stop\W+listening",
            "names": "",
        },
    },
    "es": {
        "name": "Spanish",
        "tts_model": "facebook/mms-tts-spa",
        "say_voice": "Paulina",
        "locale": "es-ES",
        "num_lang": "es",
        "lines": {
            "dictation_hint": ("Para escuchar “Agente” en español sin enviar audio fuera de este Mac, añade español en Ajustes del Sistema > Teclado > Dictado > Idiomas. Mientras tanto, di “Deskwright” como en inglés."),
            "yes": "¿Sí?",
            "clicking": "Haciendo clic", "double_clicking": "Haciendo doble clic", "right_clicking": "Clic derecho",
            "typing_into": "Escribiendo", "pointing_at": "Señalando", "dragging": "Arrastrando",
            "opening": "Abriendo {0}", "fixing": "Algo cambió. Lo estoy arreglando.",
            "known_way": "Ya he visto esto. Volviendo.",
            "approval": "Necesito tu aprobación. {0}", "this_step": "este paso", "or": "o",
            "recording": "Grabando. Muéstrame la tarea.", "got_it": "Entendido. Preparando los pasos.",
            "done": "Listo. {0}", "stopped": "Detenido.", "declined": "De acuerdo, no lo haré.",
            "failed": "No pude terminarlo. {0}",
        },
        "commands": {
            "approve": (r"aprobar|apruebo|apruébalo|aprobado|sí|si|vale|claro|de acuerdo|hazlo|adelante|acepto|"
                        r"aceptar|confirmo|confirmar|sí por favor|está bien"),
            "decline": r"rechazar|rechazo|no|no lo hagas|déjalo|olvídalo|no gracias|cancela eso",
            "send": r"envíalo|envía(?:lo)?|enviar|manda(?:lo)?|mandar|publícalo|intro|enter",
            "stop": r"para|párale|detente|detener|alto|basta ya|cancela|cancelar|aborta|para todo|para la tarea",
            "hush": r"cállate|silencio|deja de hablar|basta|calla",
            "close": r"envía|enviar|listo|ya está|eso es todo",
            "input": r"(?:escribe|entrada|texto)",
            "teach": r"modo enseñar|enseñar|déjame enseñarte|te voy a enseñar",
            "teach_stop": r"(?:ya\W+)?(?:terminé|termine|he terminado)\W+(?:de\W+)?(?:enseñar|grabar)",
            "teach_cancel": r"cancela(?:r)?\W+(?:la\W+)?(?:enseñanza|grabación|demostración)",
            "save": r"guárdal[oa]|guardar(?:\W+(?:la\W+)?tarea)?|guarda\W+(?:la\W+)?tarea",
            "listen_off": r"deja\W+de\W+escuchar",
            "names": "agente",
        },
    },
    "fr": {
        "name": "French",
        "tts_model": "facebook/mms-tts-fra",
        "say_voice": "Thomas",
        "locale": "fr-FR",
        "num_lang": "fr",
        "lines": {
            "dictation_hint": ("Pour entendre « Deskwright » en français sans envoyer d'audio hors de ce Mac, ajoute le français dans Réglages Système > Clavier > Dictée > Langues. En attendant, dis « Deskwright » à l'anglaise."),
            "yes": "Oui ?",
            "clicking": "Je clique", "double_clicking": "Double-clic", "right_clicking": "Clic droit",
            "typing_into": "Je saisis", "pointing_at": "Je pointe", "dragging": "Je fais glisser",
            "opening": "J'ouvre {0}", "fixing": "Quelque chose a changé. Je corrige.",
            "known_way": "Je connais ça. Je reviens en arrière.",
            "approval": "J'ai besoin de ton accord. {0}", "this_step": "cette étape", "or": "ou",
            "recording": "J'enregistre. Montre-moi la tâche.", "got_it": "Compris. Je prépare les étapes.",
            "done": "C'est fait. {0}", "stopped": "Arrêté.", "declined": "D'accord, je ne le fais pas.",
            "failed": "Je n'ai pas pu terminer. {0}",
        },
        "commands": {
            "approve": (r"approuver|j'approuve|approuvé|oui|ouais|d'accord|ok|vas-y|vas y|fais-le|fais le|"
                        r"accepte|accepter|confirme|confirmer|oui s'il te plaît|c'est bon"),
            "decline": r"refuser|je refuse|refuse|non|ne le fais pas|laisse tomber|non merci|annule ça",
            "send": r"envoie(?:-le| le)?|envoyer|valide|entrée|publie(?:-le)?",
            "stop": r"stop|arrête|arrêter|arrête tout|annule|annuler|halte|abandonne|arrête la tâche",
            "hush": r"tais-toi|tais toi|silence|chut|arrête de parler|ça suffit",
            "close": r"envoie|envoyer|terminé|c'est tout|voilà",
            "input": r"(?:saisie|écris|tape)",
            "teach": r"mode apprentissage|apprendre|laisse-moi t'apprendre|laisse moi t'apprendre|je vais te montrer",
            "teach_stop": r"(?:j'ai\W+)?(?:fini|terminé)\W+(?:d'|de\W+)?(?:apprendre|montrer|enregistrer)",
            "teach_cancel": r"annule(?:r)?\W+(?:l'|la\W+)?(?:apprentissage|enregistrement|démonstration)",
            "save": r"enregistre(?:-la|-le| la| le)?(?:\W+(?:la\W+|comme\W+)?tâche)?|sauvegarde(?:\W+(?:la\W+)?tâche)?",
            "listen_off": r"arrête\W+d'écouter",
            "names": "",
        },
    },
    "de": {
        "name": "German",
        "tts_model": "facebook/mms-tts-deu",
        "say_voice": "Anna",
        "locale": "de-DE",
        "num_lang": "de",
        "lines": {
            "dictation_hint": ("Damit „Deskwright“ auf Deutsch erkannt wird, ohne Audio vom Mac zu senden, füge Deutsch unter Systemeinstellungen > Tastatur > Diktat > Sprachen hinzu. Bis dahin sag „Deskwright“ englisch ausgesprochen."),
            "yes": "Ja?",
            "clicking": "Ich klicke", "double_clicking": "Doppelklick", "right_clicking": "Rechtsklick",
            "typing_into": "Ich tippe in", "pointing_at": "Ich zeige auf", "dragging": "Ich ziehe",
            "opening": "Ich öffne {0}", "fixing": "Etwas hat sich geändert. Ich korrigiere das.",
            "known_way": "Das kenne ich schon. Ich gehe zurück.",
            "approval": "Ich brauche deine Zustimmung. {0}", "this_step": "diesen Schritt", "or": "oder",
            "recording": "Ich nehme auf. Zeig mir die Aufgabe.", "got_it": "Verstanden. Ich plane die Schritte.",
            "done": "Fertig. {0}", "stopped": "Gestoppt.", "declined": "Okay, das mache ich nicht.",
            "failed": "Das konnte ich nicht abschließen. {0}",
        },
        "commands": {
            "approve": (r"genehmigen|genehmigt|zustimmen|ja|jawohl|okay|ok|klar|mach es|mach das|mach weiter|los|"
                        r"bestätigen|bestätigt|akzeptieren|ja bitte|passt"),
            "decline": r"ablehnen|abgelehnt|nein|nicht|mach das nicht|lass es|vergiss es|nein danke",
            "send": r"senden|sende(?: es)?|schick(?:en| es| ab)?|abschicken|eingabe|enter",
            "stop": r"stopp|stop|halt|anhalten|abbrechen|brich ab|aufhören|hör auf|alles stoppen",
            "hush": r"sei still|ruhe|still|hör auf zu reden|psst|genug",
            "close": r"senden|fertig|das wars|das war's|abschicken",
            "input": r"(?:eingabe|schreib|tippe)",
            "teach": r"lernmodus|beibringen|lass mich dir zeigen|ich zeige es dir",
            "teach_stop": r"(?:ich\W+bin\W+)?fertig\W+mit\W+(?:dem\W+)?(?:zeigen|aufnehmen|beibringen)",
            "teach_cancel": r"(?:aufnahme|vorführung|lernmodus)\W+abbrechen",
            "save": r"speicher(?:n|e)?(?:\W+(?:es|das))?(?:\W+als\W+aufgabe|\W+(?:die\W+)?aufgabe)?",
            "listen_off": r"hör\W+auf\W+zuzuhören|nicht\W+mehr\W+zuhören",
            "names": "",
        },
    },
    "pt": {
        "name": "Portuguese",
        "tts_model": "facebook/mms-tts-por",
        "say_voice": "Luciana",
        "locale": "pt-BR",
        "num_lang": "pt_BR",
        "lines": {
            "dictation_hint": ("Para ouvir “Agente” em português sem enviar áudio para fora deste Mac, adicione português em Ajustes do Sistema > Teclado > Ditado > Idiomas. Enquanto isso, diga “Deskwright” como em inglês."),
            "yes": "Sim?",
            "clicking": "Clicando", "double_clicking": "Clique duplo", "right_clicking": "Clique direito",
            "typing_into": "Digitando em", "pointing_at": "Apontando para", "dragging": "Arrastando",
            "opening": "Abrindo {0}", "fixing": "Algo mudou. Estou corrigindo.",
            "known_way": "Já vi isso antes. Voltando.",
            "approval": "Preciso da sua aprovação. {0}", "this_step": "esta etapa", "or": "ou",
            "recording": "Gravando. Mostre a tarefa.", "got_it": "Entendi. Montando os passos.",
            "done": "Pronto. {0}", "stopped": "Parado.", "declined": "Tudo bem, não vou fazer isso.",
            "failed": "Não consegui terminar. {0}",
        },
        "commands": {
            "approve": (r"aprovar|aprovo|aprovado|sim|claro|ok|pode|pode fazer|faça|faz|vai em frente|aceito|"
                        r"aceitar|confirmo|confirmar|sim por favor|tudo bem"),
            "decline": r"recusar|recuso|rejeitar|não|nao|não faça|deixa pra lá|esquece|não obrigado",
            "send": r"envia(?:r)?|envie|manda(?:r)?|mande|publica|enter",
            "stop": r"para|pare|parar|chega|cancela(?:r)?|aborta|para tudo|pare a tarefa",
            "hush": r"cala a boca|silêncio|silencio|para de falar|pare de falar|quieto",
            "close": r"envia|enviar|pronto|é isso",
            "input": r"(?:entrada|escreve|escreva|digite)",
            "teach": r"modo ensinar|ensinar|deixa eu te ensinar|deixe-me ensinar|vou te mostrar",
            "teach_stop": r"(?:já\W+)?(?:terminei|acabei)\W+de\W+(?:ensinar|gravar|mostrar)",
            "teach_cancel": r"cancela(?:r)?\W+(?:a\W+)?(?:gravação|demonstração|aula)",
            "save": r"salva(?:r)?(?:\W+(?:isso|a))?(?:\W+(?:a\W+|como\W+)?tarefa)?|guarda(?:r)?\W+(?:a\W+)?tarefa",
            "listen_off": r"para\W+de\W+ouvir|pare\W+de\W+ouvir",
            "names": "agente",
        },
    },
    "zh": {
        "name": "Simplified Chinese",
        "tts_model": "",  # MMS-TTS has no Mandarin checkpoint: the Mac's own Chinese voice talks instead
        "say_voice": "Tingting",
        "locale": "zh-CN",
        "num_lang": "",  # Chinese voices read digits themselves
        "lines": {
            "dictation_hint": ("要在不把音频发出本机的情况下听懂中文指令，请在“系统设置 > 键盘 > 听写 > 语言”中添加中文。在此之前，请用英语发音说“Deskwright”。"),
            "yes": "在呢？",
            "clicking": "正在点击", "double_clicking": "正在双击", "right_clicking": "正在右键点击",
            "typing_into": "正在输入", "pointing_at": "正在指向", "dragging": "正在拖动",
            "opening": "正在打开{0}", "fixing": "有变化，正在修正。", "known_way": "这个我见过，正在返回。",
            "approval": "需要你的批准。{0}", "this_step": "这一步", "or": "或者",
            "recording": "正在录制，请演示任务。", "got_it": "明白了，正在整理步骤。",
            "done": "完成了。{0}", "stopped": "已停止。", "declined": "好的，我不会做。",
            "failed": "没能完成。{0}",
        },
        "commands": {
            "approve": r"批准|同意|是的|是|好的|好|可以|行|做吧|确认|没问题|继续",
            "decline": r"拒绝|不要|不|不用了|算了|别做",
            "send": r"发送|发出去|发吧|提交|回车",
            "stop": r"停止|停下|停|取消|别做了|中止|全部停止",
            "hush": r"别说了|安静|闭嘴|够了",
            "close": r"发送|好了|就这样",
            "input": r"(?:输入|打字)",
            "teach": r"教学模式|我来教你|让我教你",
            "teach_stop": r"(?:我)?(?:教完了|录完了|演示完了)",
            "teach_cancel": r"取消(?:教学|录制|演示)",
            "save": r"保存(?:任务|这个|一下)?",
            "listen_off": r"停止监听|别听了",
            "names": "代理",
        },
    },
}


def lang() -> str:
    return config.language if config.language in LANGUAGES else "en"


def info(code: str | None = None) -> dict:
    return LANGUAGES.get(code or lang(), LANGUAGES["en"])


def line(key: str, *args) -> str:
    """A narrator line in the current language."""
    text = info()["lines"].get(key) or LANGUAGES["en"]["lines"][key]
    return text.format(*args) if args else text


def answer_in() -> str:
    """For model prompts: the language the user reads and hears. Empty for English, the default."""
    return "" if lang() == "en" else info()["name"]
