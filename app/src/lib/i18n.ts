// The app's text in Deskwright's languages. t("English text", { n: 3 }) returns it in the current language; the
// English text is the key, so a string without a translation shows in English. The engine localizes what it says
// (engine/i18n.py); run statuses it sends are translated here by their prefix (tStatus).

export type Lang = "en" | "es" | "fr" | "de" | "pt" | "zh";

export const LANGUAGES: { code: Lang; name: string }[] = [
  { code: "en", name: "English" },
  { code: "es", name: "Español" },
  { code: "fr", name: "Français" },
  { code: "de", name: "Deutsch" },
  { code: "pt", name: "Português" },
  { code: "zh", name: "中文（简体）" },
];

const ORDER: Lang[] = ["es", "fr", "de", "pt", "zh"];

// English -> [Spanish, French, German, Portuguese, Chinese]
const D: Record<string, [string, string, string, string, string]> = {
  // Header, menu, empty state
  "Language": ["Idioma", "Langue", "Sprache", "Idioma", "语言"],
  "Engine offline": ["Motor desconectado", "Moteur hors ligne", "Engine offline", "Motor offline", "引擎离线"],
  "Connecting…": ["Conectando…", "Connexion…", "Verbinde…", "Conectando…", "正在连接…"],
  "Sensitive actions run without asking. Click to turn approvals back on.": [
    "Las acciones sensibles se ejecutan sin preguntar. Haz clic para volver a activar las aprobaciones.",
    "Les actions sensibles s'exécutent sans demander. Clique pour réactiver les validations.",
    "Heikle Aktionen laufen ohne Rückfrage. Klicke, um Freigaben wieder einzuschalten.",
    "Ações sensíveis são executadas sem perguntar. Clique para reativar as aprovações.",
    "敏感操作将不经询问直接执行。点击重新开启批准。",
  ],
  "Approvals off": ["Aprobaciones desactivadas", "Validations désactivées", "Freigaben aus", "Aprovações desligadas", "批准已关闭"],
  "Working": ["Trabajando", "En cours", "Arbeitet", "Trabalhando", "工作中"],
  "New conversation": ["Nueva conversación", "Nouvelle conversation", "Neue Unterhaltung", "Nova conversa", "新对话"],
  "More": ["Más", "Plus", "Mehr", "Mais", "更多"],
  "Collapse": ["Contraer", "Réduire", "Einklappen", "Recolher", "收起"],
  "Finish demonstration": ["Terminar demostración", "Terminer la démonstration", "Vorführung beenden", "Concluir demonstração", "结束演示"],
  "Teach by demonstration": ["Enseñar con una demostración", "Apprendre par démonstration", "Durch Vorführen beibringen", "Ensinar por demonstração", "通过演示来教"],
  "Saved tasks": ["Tareas guardadas", "Tâches enregistrées", "Gespeicherte Aufgaben", "Tarefas salvas", "已保存的任务"],
  "Run metrics": ["Métricas de ejecución", "Statistiques d'exécution", "Laufstatistik", "Métricas de execução", "运行统计"],
  "Permissions": ["Permisos", "Autorisations", "Berechtigungen", "Permissões", "权限"],
  "Listen for “Hey Agent”": ["Escuchar “Hey Agent”", "Écouter « Hey Agent »", "Auf „Hey Agent“ hören", "Ouvir “Hey Agent”", "监听“Hey Agent”"],
  "Stop listening for “Hey Agent”": ["Dejar de escuchar “Hey Agent”", "Ne plus écouter « Hey Agent »", "Nicht mehr auf „Hey Agent“ hören", "Parar de ouvir “Hey Agent”", "停止监听“Hey Agent”"],
  "Speak out loud": ["Hablar en voz alta", "Parler à voix haute", "Laut sprechen", "Falar em voz alta", "朗读出声"],
  "Speak out loud (loading voice…)": ["Hablar en voz alta (cargando voz…)", "Parler à voix haute (chargement de la voix…)", "Laut sprechen (Stimme lädt…)", "Falar em voz alta (carregando voz…)", "朗读出声（正在加载语音…）"],
  "Review before running": ["Revisar antes de ejecutar", "Vérifier avant d'exécuter", "Vor dem Ausführen prüfen", "Revisar antes de executar", "运行前先审阅"],
  "Skip approvals": ["Omitir aprobaciones", "Ignorer les validations", "Freigaben überspringen", "Pular aprovações", "跳过批准"],
  "Quit Deskwright": ["Salir de Deskwright", "Quitter Deskwright", "Deskwright beenden", "Sair do Deskwright", "退出 Deskwright"],
  "What should I do?": ["¿Qué hago?", "Que dois-je faire ?", "Was soll ich tun?", "O que devo fazer?", "要我做什么？"],
  "Describe a task and I'll take control.": ["Describe una tarea y tomaré el control.", "Décris une tâche et je prends le contrôle.", "Beschreib eine Aufgabe und ich übernehme.", "Descreva uma tarefa e eu assumo o controle.", "描述一个任务，我来操作。"],
  "Thinking…": ["Pensando…", "Réflexion…", "Denke nach…", "Pensando…", "思考中…"],
  "Analysing your demonstration": ["Analizando tu demostración", "Analyse de ta démonstration", "Analysiere deine Vorführung", "Analisando sua demonstração", "正在分析你的演示"],
  "Close": ["Cerrar", "Fermer", "Schließen", "Fechar", "关闭"],

  // Run narration in the chat
  "Running your saved task.": ["Ejecutando tu tarea guardada.", "J'exécute ta tâche enregistrée.", "Deine gespeicherte Aufgabe läuft.", "Executando sua tarefa salva.", "正在运行你保存的任务。"],
  "Ran your saved task.": ["Ejecuté tu tarea guardada.", "J'ai exécuté ta tâche enregistrée.", "Deine gespeicherte Aufgabe ist gelaufen.", "Executei sua tarefa salva.", "已运行你保存的任务。"],
  "I wrote a program for this and I'm running it on your screen.": [
    "Escribí un programa para esto y lo estoy ejecutando en tu pantalla.",
    "J'ai écrit un programme pour ça et je l'exécute sur ton écran.",
    "Ich habe dafür ein Programm geschrieben und führe es auf deinem Bildschirm aus.",
    "Escrevi um programa para isso e estou executando na sua tela.",
    "我为此写了一个程序，正在你的屏幕上运行。",
  ],
  "Here's the program I wrote and ran.": ["Este es el programa que escribí y ejecuté.", "Voici le programme que j'ai écrit et exécuté.", "Hier ist das Programm, das ich geschrieben und ausgeführt habe.", "Aqui está o programa que escrevi e executei.", "这是我编写并运行的程序。"],
  "Here's the program. Review it, then run it.": ["Aquí está el programa. Revísalo y luego ejecútalo.", "Voici le programme. Vérifie-le, puis exécute-le.", "Hier ist das Programm. Prüf es und führ es dann aus.", "Aqui está o programa. Revise e depois execute.", "程序在这里。请先审阅，然后运行。"],
  "Stage {i} of {n}": ["Etapa {i} de {n}", "Étape {i} sur {n}", "Schritt {i} von {n}", "Etapa {i} de {n}", "第 {i} 阶段，共 {n} 个"],
  "Writing the program…": ["Escribiendo el programa…", "Écriture du programme…", "Schreibe das Programm…", "Escrevendo o programa…", "正在编写程序…"],
  "Verified": ["Verificado", "Vérifié", "Bestätigt", "Verificado", "已验证"],
  "Not verified": ["No verificado", "Non vérifié", "Nicht bestätigt", "Não verificado", "未验证"],
  "Expected": ["Esperado", "Attendu", "Erwartet", "Esperado", "预期"],
  "Saw": ["Visto", "Vu", "Gesehen", "Visto", "看到"],
  "{a} of {b} records": ["{a} de {b} registros", "{a} sur {b} enregistrements", "{a} von {b} Einträgen", "{a} de {b} registros", "{b} 条记录中的 {a} 条"],
  "1 fix": ["1 corrección", "1 correction", "1 Korrektur", "1 correção", "1 次修正"],
  "{n} fixes": ["{n} correcciones", "{n} corrections", "{n} Korrekturen", "{n} correções", "{n} 次修正"],
  "Edit": ["Editar", "Modifier", "Bearbeiten", "Editar", "编辑"],
  "Copy": ["Copiar", "Copier", "Kopieren", "Copiar", "复制"],
  "Copied": ["Copiado", "Copié", "Kopiert", "Copiado", "已复制"],
  "Took a learned way back to line {n}.": ["Tomé un camino aprendido de vuelta a la línea {n}.", "J'ai pris un chemin appris pour revenir à la ligne {n}.", "Bin über einen gelernten Weg zu Zeile {n} zurück.", "Usei um caminho aprendido de volta à linha {n}.", "通过学到的路径回到第 {n} 行。"],
  "Rewrote from line {n} and resumed.": ["Reescribí desde la línea {n} y continué.", "J'ai réécrit à partir de la ligne {n} et repris.", "Ab Zeile {n} neu geschrieben und fortgesetzt.", "Reescrevi a partir da linha {n} e continuei.", "从第 {n} 行起重写并继续。"],
  "1 line replaced by the rewrite below": ["1 línea reemplazada por la reescritura de abajo", "1 ligne remplacée par la réécriture ci-dessous", "1 Zeile durch die Neufassung unten ersetzt", "1 linha substituída pela reescrita abaixo", "1 行已被下方重写替换"],
  "{n} lines replaced by the rewrite below": ["{n} líneas reemplazadas por la reescritura de abajo", "{n} lignes remplacées par la réécriture ci-dessous", "{n} Zeilen durch die Neufassung unten ersetzt", "{n} linhas substituídas pela reescrita abaixo", "{n} 行已被下方重写替换"],
  "Name this task": ["Ponle nombre a esta tarea", "Nomme cette tâche", "Aufgabe benennen", "Dê um nome a esta tarefa", "为此任务命名"],
  "Save": ["Guardar", "Enregistrer", "Speichern", "Salvar", "保存"],
  "Cancel": ["Cancelar", "Annuler", "Abbrechen", "Cancelar", "取消"],
  "Run": ["Ejecutar", "Exécuter", "Ausführen", "Executar", "运行"],
  "Save as task": ["Guardar como tarea", "Enregistrer comme tâche", "Als Aufgabe speichern", "Salvar como tarefa", "保存为任务"],
  "or say “start”": ["o di “empieza”", "ou dis « commence »", "oder sag „start“", "ou diga “começar”", "或说“开始”"],

  // Cards
  "Show in Finder": ["Mostrar en Finder", "Afficher dans le Finder", "Im Finder zeigen", "Mostrar no Finder", "在访达中显示"],
  "You answered: {a}": ["Respondiste: {a}", "Tu as répondu : {a}", "Deine Antwort: {a}", "Você respondeu: {a}", "你的回答：{a}"],
  "No longer needed": ["Ya no es necesario", "Plus nécessaire", "Nicht mehr nötig", "Não é mais necessário", "已不再需要"],
  "Reply…": ["Responder…", "Répondre…", "Antworten…", "Responder…", "回复…"],
  "Approved": ["Aprobado", "Validé", "Freigegeben", "Aprovado", "已批准"],
  "Declined": ["Rechazado", "Refusé", "Abgelehnt", "Recusado", "已拒绝"],
  "Closed": ["Cerrado", "Fermé", "Geschlossen", "Fechado", "已关闭"],
  "Approve this action?": ["¿Apruebas esta acción?", "Valider cette action ?", "Diese Aktion freigeben?", "Aprovar esta ação?", "批准此操作？"],
  "Approve": ["Aprobar", "Valider", "Freigeben", "Aprovar", "批准"],
  "Decline": ["Rechazar", "Refuser", "Ablehnen", "Recusar", "拒绝"],
  "Approve all this run": ["Aprobar todo en esta ejecución", "Tout valider pour cette exécution", "Alles in diesem Lauf freigeben", "Aprovar tudo nesta execução", "本次运行全部批准"],
  "Done in {s}s": ["Listo en {s} s", "Terminé en {s} s", "Fertig in {s} s", "Concluído em {s} s", "用时 {s} 秒完成"],
  "Stopped": ["Detenido", "Arrêté", "Gestoppt", "Parado", "已停止"],
  "Stopped: you declined an action": ["Detenido: rechazaste una acción", "Arrêté : tu as refusé une action", "Gestoppt: du hast eine Aktion abgelehnt", "Parado: você recusou uma ação", "已停止：你拒绝了一个操作"],
  "Couldn't finish": ["No se pudo terminar", "Impossible de terminer", "Nicht abgeschlossen", "Não foi possível concluir", "未能完成"],
  "Save as a reusable task": ["Guardar como tarea reutilizable", "Enregistrer comme tâche réutilisable", "Als wiederverwendbare Aufgabe speichern", "Salvar como tarefa reutilizável", "保存为可复用的任务"],
  "Continue after “{name}”": ["Continuar después de “{name}”", "Reprendre après « {name} »", "Nach „{name}“ fortsetzen", "Continuar depois de “{name}”", "从“{name}”之后继续"],
  "{n} steps": ["{n} pasos", "{n} étapes", "{n} Schritte", "{n} passos", "{n} 步"],
  "{n} model calls": ["{n} llamadas al modelo", "{n} appels au modèle", "{n} Modellaufrufe", "{n} chamadas ao modelo", "{n} 次模型调用"],
  "{n}% from cache": ["{n}% desde la caché", "{n} % depuis le cache", "{n} % aus dem Cache", "{n}% do cache", "{n}% 来自缓存"],
  "{a}/{b} self-fixes worked": ["{a}/{b} autocorrecciones funcionaron", "{a}/{b} auto-corrections ont fonctionné", "{a}/{b} Selbstkorrekturen haben geklappt", "{a}/{b} autocorreções funcionaram", "{a}/{b} 次自我修正成功"],
  "Run {n}: {x}× faster than run 1": ["Ejecución {n}: {x}× más rápida que la 1", "Exécution {n} : {x}× plus rapide que la 1", "Lauf {n}: {x}× schneller als Lauf 1", "Execução {n}: {x}× mais rápida que a 1", "第 {n} 次运行：比第 1 次快 {x} 倍"],
  "Run {n}: {x}× faster, {p}% cheaper than run 1": ["Ejecución {n}: {x}× más rápida y {p}% más barata que la 1", "Exécution {n} : {x}× plus rapide et {p} % moins chère que la 1", "Lauf {n}: {x}× schneller und {p} % günstiger als Lauf 1", "Execução {n}: {x}× mais rápida e {p}% mais barata que a 1", "第 {n} 次运行：比第 1 次快 {x} 倍，便宜 {p}%"],
  "The position cache skipped {n} model calls (about {s}s, {c}).": [
    "La caché de posiciones evitó {n} llamadas al modelo (unos {s} s, {c}).",
    "Le cache de positions a évité {n} appels au modèle (environ {s} s, {c}).",
    "Der Positions-Cache hat {n} Modellaufrufe gespart (etwa {s} s, {c}).",
    "O cache de posições evitou {n} chamadas ao modelo (cerca de {s} s, {c}).",
    "位置缓存省去了 {n} 次模型调用（约 {s} 秒，{c}）。",
  ],
  "Saved as “{name}”. Say “run {name}” any time.": [
    "Guardada como “{name}”. Di “ejecuta {name}” cuando quieras.",
    "Enregistrée sous « {name} ». Dis « lance {name} » quand tu veux.",
    "Gespeichert als „{name}“. Sag jederzeit „führe {name} aus“.",
    "Salva como “{name}”. Diga “execute {name}” quando quiser.",
    "已保存为“{name}”。随时说“运行{name}”即可。",
  ],
  "I watched your demonstration ({n} steps) and turned it into a program. Recorded values became variables, so it can run on new records.": [
    "Vi tu demostración ({n} pasos) y la convertí en un programa. Los valores grabados son variables, así que puede usarse con registros nuevos.",
    "J'ai regardé ta démonstration ({n} étapes) et l'ai transformée en programme. Les valeurs enregistrées sont devenues des variables, il peut donc traiter de nouveaux enregistrements.",
    "Ich habe deine Vorführung ({n} Schritte) angesehen und in ein Programm verwandelt. Aufgezeichnete Werte wurden zu Variablen, also läuft es auch mit neuen Einträgen.",
    "Assisti à sua demonstração ({n} passos) e transformei em um programa. Os valores gravados viraram variáveis, então ele funciona com novos registros.",
    "我看了你的演示（{n} 步）并把它变成了程序。录到的值已变成变量，所以可以用于新的记录。",
  ],
  "and {n} more": ["y {n} más", "et {n} de plus", "und {n} weitere", "e mais {n}", "还有 {n} 步"],
  "Needs a quick edit: {p}": ["Necesita un pequeño ajuste: {p}", "Une petite retouche est nécessaire : {p}", "Braucht eine kleine Änderung: {p}", "Precisa de um pequeno ajuste: {p}", "需要稍作修改：{p}"],

  // Composer
  "Show saved tasks": ["Mostrar tareas guardadas", "Afficher les tâches enregistrées", "Gespeicherte Aufgaben zeigen", "Mostrar tarefas salvas", "显示已保存的任务"],
  "Show run metrics": ["Mostrar métricas", "Afficher les statistiques", "Laufstatistik zeigen", "Mostrar métricas", "显示运行统计"],
  "Run scripts right away": ["Ejecutar los programas al momento", "Exécuter les programmes tout de suite", "Programme sofort ausführen", "Executar os programas na hora", "立即运行程序"],
  "Clear the conversation": ["Borrar la conversación", "Effacer la conversation", "Unterhaltung löschen", "Limpar a conversa", "清空对话"],
  "Working on it…": ["Trabajando en ello…", "Je m'en occupe…", "Bin dran…", "Trabalhando nisso…", "正在处理…"],
  "Say “Agent…” or type a task": ["Di “Agente…” o escribe una tarea", "Dis « Agent… » ou tape une tâche", "Sag „Agent…“ oder tippe eine Aufgabe", "Diga “Agente…” ou digite uma tarefa", "说“Agent…”或输入任务"],
  "Ask Agent to do something": ["Pídele algo a Deskwright", "Demande quelque chose à Deskwright", "Bitte Deskwright um etwas", "Peça algo ao Deskwright", "让 Deskwright 做点什么"],
  "Recording your demonstration · {t}": ["Grabando tu demostración · {t}", "Enregistrement de ta démonstration · {t}", "Deine Vorführung wird aufgenommen · {t}", "Gravando sua demonstração · {t}", "正在录制你的演示 · {t}"],
  "Do the task once in any app.": ["Haz la tarea una vez en cualquier app.", "Fais la tâche une fois dans n'importe quelle app.", "Mach die Aufgabe einmal in einer beliebigen App.", "Faça a tarefa uma vez em qualquer app.", "在任意应用中完成一次任务。"],
  "Finish": ["Terminar", "Terminer", "Fertig", "Concluir", "完成"],
  "Cancel (esc)": ["Cancelar (esc)", "Annuler (esc)", "Abbrechen (esc)", "Cancelar (esc)", "取消 (esc)"],
  "Send": ["Enviar", "Envoyer", "Senden", "Enviar", "发送"],
  "Press esc or say “stop” to stop": ["Pulsa esc o di “para” para detener", "Appuie sur esc ou dis « stop » pour arrêter", "Drück esc oder sag „stopp“ zum Anhalten", "Pressione esc ou diga “pare” para parar", "按 esc 或说“停止”来停止"],
  "Press esc to stop": ["Pulsa esc para detener", "Appuie sur esc pour arrêter", "Drück esc zum Anhalten", "Pressione esc para parar", "按 esc 停止"],
  "Approvals are off: sensitive actions run without asking.": ["Las aprobaciones están desactivadas: las acciones sensibles se ejecutan sin preguntar.", "Les validations sont désactivées : les actions sensibles s'exécutent sans demander.", "Freigaben sind aus: heikle Aktionen laufen ohne Rückfrage.", "As aprovações estão desligadas: ações sensíveis rodam sem perguntar.", "批准已关闭：敏感操作将直接执行。"],

  // Corner bar
  "Open panel": ["Abrir panel", "Ouvrir le panneau", "Panel öffnen", "Abrir painel", "打开面板"],
  "Open panel (connecting…)": ["Abrir panel (conectando…)", "Ouvrir le panneau (connexion…)", "Panel öffnen (verbinde…)", "Abrir painel (conectando…)", "打开面板（正在连接…）"],
  "Working…": ["Trabajando…", "En cours…", "Arbeitet…", "Trabalhando…", "工作中…"],
  "Press": ["Pulsa", "Appuie sur", "Drück", "Pressione", "按"],
  "to stop": ["para detener", "pour arrêter", "zum Anhalten", "para parar", "停止"],
  "or say “stop” to stop": ["o di “para” para detener", "ou dis « stop » pour arrêter", "oder sag „stopp“ zum Anhalten", "ou diga “pare” para parar", "或说“停止”来停止"],
  "{n} cached": ["{n} en caché", "{n} en cache", "{n} aus dem Cache", "{n} em cache", "{n} 次来自缓存"],
  "{n} calls": ["{n} llamadas", "{n} appels", "{n} Aufrufe", "{n} chamadas", "{n} 次调用"],
  "Listening: say “stop” to stop": ["Escuchando: di “para” para detener", "À l'écoute : dis « stop » pour arrêter", "Hört zu: sag „stopp“ zum Anhalten", "Ouvindo: diga “pare” para parar", "正在聆听：说“停止”即可停止"],

  // Results
  "Export": ["Exportar", "Exporter", "Exportieren", "Exportar", "导出"],
  "Copy to clipboard": ["Copiar al portapapeles", "Copier dans le presse-papiers", "In die Zwischenablage", "Copiar para a área de transferência", "复制到剪贴板"],
  "Table": ["Tabla", "Tableau", "Tabelle", "Tabela", "表格"],
  "1 row": ["1 fila", "1 ligne", "1 Zeile", "1 linha", "1 行"],
  "{n} rows": ["{n} filas", "{n} lignes", "{n} Zeilen", "{n} linhas", "{n} 行"],
  "From the position cache": ["Desde la caché de posiciones", "Depuis le cache de positions", "Aus dem Positions-Cache", "Do cache de posições", "来自位置缓存"],
  "Found by the vision models": ["Encontrado por los modelos de visión", "Trouvé par les modèles de vision", "Von den Bildmodellen gefunden", "Encontrado pelos modelos de visão", "由视觉模型找到"],
  "Copied to the clipboard": ["Copiado al portapapeles", "Copié dans le presse-papiers", "In die Zwischenablage kopiert", "Copiado para a área de transferência", "已复制到剪贴板"],
  "Exported the task's code (run it from other apps with deskwright.py)": [
    "Exporté el código de la tarea (ejecútalo desde otras apps con deskwright.py)",
    "Code de la tâche exporté (lance-le depuis d'autres apps avec deskwright.py)",
    "Code der Aufgabe exportiert (aus anderen Apps mit deskwright.py ausführen)",
    "Código da tarefa exportado (execute em outros apps com deskwright.py)",
    "已导出任务代码（可在其他应用中用 deskwright.py 运行）",
  ],
  "Exported {f}": ["Exportado {f}", "{f} exporté", "{f} exportiert", "{f} exportado", "已导出 {f}"],

  // Saved tasks and metrics
  "No saved tasks yet. Save a finished run, or teach me one: open the … menu and choose": [
    "Aún no hay tareas guardadas. Guarda una ejecución terminada o enséñame una: abre el menú … y elige",
    "Aucune tâche enregistrée. Enregistre une exécution terminée ou apprends-m'en une : ouvre le menu … et choisis",
    "Noch keine gespeicherten Aufgaben. Speichere einen fertigen Lauf oder bring mir eine bei: öffne das Menü … und wähle",
    "Nenhuma tarefa salva ainda. Salve uma execução concluída ou me ensine uma: abra o menu … e escolha",
    "还没有保存的任务。保存一次完成的运行，或者教我一个：打开 … 菜单并选择",
  ],
  "1 run": ["1 ejecución", "1 exécution", "1 Lauf", "1 execução", "1 次运行"],
  "{n} runs": ["{n} ejecuciones", "{n} exécutions", "{n} Läufe", "{n} execuções", "{n} 次运行"],
  "1 way back learned": ["1 camino de vuelta aprendido", "1 chemin de retour appris", "1 Rückweg gelernt", "1 caminho de volta aprendido", "已学会 1 条返回路径"],
  "{n} ways back learned": ["{n} caminos de vuelta aprendidos", "{n} chemins de retour appris", "{n} Rückwege gelernt", "{n} caminhos de volta aprendidos", "已学会 {n} 条返回路径"],
  "now {x}× faster": ["ahora {x}× más rápida", "désormais {x}× plus rapide", "jetzt {x}× schneller", "agora {x}× mais rápida", "现在快 {x} 倍"],
  "time": ["tiempo", "temps", "Zeit", "tempo", "时间"],
  "cost": ["coste", "coût", "Kosten", "custo", "费用"],
  "Latest: {note}": ["Última: {note}", "Dernière : {note}", "Neueste: {note}", "Mais recente: {note}", "最新：{note}"],
  "Original version": ["Versión original", "Version d'origine", "Ursprüngliche Version", "Versão original", "原始版本"],
  "Export code": ["Exportar código", "Exporter le code", "Code exportieren", "Exportar código", "导出代码"],
  "Delete": ["Eliminar", "Supprimer", "Löschen", "Excluir", "删除"],
  "Here's how the last run went.": ["Así fue la última ejecución.", "Voici comment s'est passée la dernière exécution.", "So lief der letzte Lauf.", "Veja como foi a última execução.", "上一次运行的情况如下。"],
  "No runs yet this session.": ["Todavía no hay ejecuciones en esta sesión.", "Aucune exécution pour l'instant.", "In dieser Sitzung noch keine Läufe.", "Nenhuma execução nesta sessão ainda.", "本次会话还没有运行。"],
  "Time": ["Tiempo", "Temps", "Zeit", "Tempo", "时间"],
  "{s}s in models": ["{s} s en modelos", "{s} s dans les modèles", "{s} s in Modellen", "{s} s nos modelos", "模型用时 {s} 秒"],
  "Cost": ["Coste", "Coût", "Kosten", "Custo", "费用"],
  "Steps": ["Pasos", "Étapes", "Schritte", "Passos", "步骤"],
  "Model calls": ["Llamadas al modelo", "Appels au modèle", "Modellaufrufe", "Chamadas ao modelo", "模型调用"],
  "From cache": ["Desde caché", "Depuis le cache", "Aus dem Cache", "Do cache", "来自缓存"],
  "{n} calls skipped": ["{n} llamadas evitadas", "{n} appels évités", "{n} Aufrufe gespart", "{n} chamadas evitadas", "省去 {n} 次调用"],
  "Self-fixes": ["Autocorrecciones", "Auto-corrections", "Selbstkorrekturen", "Autocorreções", "自我修正"],
  "worked / tried": ["funcionaron / intentadas", "réussies / tentées", "geklappt / versucht", "funcionaram / tentadas", "成功 / 尝试"],
  "Across all {n} runs: {a}% succeeded, and {b}% of self-fixes worked.": [
    "En las {n} ejecuciones: {a}% salieron bien y {b}% de las autocorrecciones funcionaron.",
    "Sur les {n} exécutions : {a} % ont réussi et {b} % des auto-corrections ont fonctionné.",
    "Über alle {n} Läufe: {a} % erfolgreich, {b} % der Selbstkorrekturen haben geklappt.",
    "Em todas as {n} execuções: {a}% deram certo e {b}% das autocorreções funcionaram.",
    "全部 {n} 次运行：{a}% 成功，{b}% 的自我修正有效。",
  ],
  "Clear the position cache": ["Borrar la caché de posiciones", "Vider le cache de positions", "Positions-Cache leeren", "Limpar o cache de posições", "清除位置缓存"],
  "No runs yet": ["Aún no hay ejecuciones", "Aucune exécution", "Noch keine Läufe", "Nenhuma execução ainda", "还没有运行"],

  // Permissions
  "Screen Recording": ["Grabación de pantalla", "Enregistrement de l'écran", "Bildschirmaufnahme", "Gravação de tela", "录屏"],
  "Accessibility": ["Accesibilidad", "Accessibilité", "Bedienungshilfen", "Acessibilidade", "辅助功能"],
  "Microphone": ["Micrófono", "Micro", "Mikrofon", "Microfone", "麦克风"],
  "Input Monitoring": ["Monitorización de entrada", "Surveillance de l'entrée", "Eingabeüberwachung", "Monitoramento de entrada", "输入监控"],
  "Speech Recognition": ["Reconocimiento de voz", "Reconnaissance vocale", "Spracherkennung", "Reconhecimento de fala", "语音识别"],
  "Automation": ["Automatización", "Automatisation", "Automation", "Automação", "自动化"],
  "to see your screen": ["para ver tu pantalla", "pour voir ton écran", "um deinen Bildschirm zu sehen", "para ver sua tela", "用于查看屏幕"],
  "to move the mouse and type": ["para mover el ratón y escribir", "pour bouger la souris et taper", "um die Maus zu bewegen und zu tippen", "para mover o mouse e digitar", "用于移动鼠标和打字"],
  "for voice, optional": ["para la voz, opcional", "pour la voix, facultatif", "für Sprache, optional", "para voz, opcional", "用于语音，可选"],
  "for teach mode": ["para el modo enseñar", "pour le mode apprentissage", "für den Lernmodus", "para o modo ensinar", "用于教学模式"],
  "Before the first run": ["Antes de la primera ejecución", "Avant la première exécution", "Vor dem ersten Lauf", "Antes da primeira execução", "首次运行之前"],
  "macOS needs to allow this app to see and control the screen. Restart the app after granting.": [
    "macOS debe permitir que esta app vea y controle la pantalla. Reinicia la app después de darle permiso.",
    "macOS doit autoriser cette app à voir et contrôler l'écran. Redémarre l'app après l'autorisation.",
    "macOS muss dieser App erlauben, den Bildschirm zu sehen und zu steuern. Starte die App danach neu.",
    "O macOS precisa permitir que este app veja e controle a tela. Reinicie o app depois de permitir.",
    "macOS 需要允许此应用查看和控制屏幕。授权后请重启应用。",
  ],
  "Open": ["Abrir", "Ouvrir", "Öffnen", "Abrir", "打开"],
  "Screen Recording is on. macOS applies it after Deskwright restarts.": [
    "La grabación de pantalla está activada. macOS la aplica cuando Deskwright se reinicia.",
    "L'enregistrement de l'écran est activé. macOS l'applique après le redémarrage de Deskwright.",
    "Bildschirmaufnahme ist an. macOS übernimmt sie nach einem Neustart von Deskwright.",
    "A gravação de tela está ativada. O macOS aplica depois que o Deskwright reiniciar.",
    "录屏已开启。Deskwright 重启后 macOS 才会生效。",
  ],
  "Restart Deskwright": ["Reiniciar Deskwright", "Redémarrer Deskwright", "Deskwright neu starten", "Reiniciar o Deskwright", "重启 Deskwright"],
  "Tip: turn on Do Not Disturb so notifications stay out of screenshots.": [
    "Consejo: activa No molestar para que las notificaciones no salgan en las capturas.",
    "Astuce : active Ne pas déranger pour que les notifications n'apparaissent pas dans les captures.",
    "Tipp: Schalte „Nicht stören“ ein, damit Mitteilungen nicht in Bildschirmfotos landen.",
    "Dica: ative Não Perturbe para que as notificações não apareçam nas capturas.",
    "提示：打开勿扰模式，避免通知出现在截图中。",
  ],
  "Done": ["Listo", "Terminé", "Fertig", "Pronto", "完成"],
  "Checking permissions…": ["Comprobando permisos…", "Vérification des autorisations…", "Prüfe Berechtigungen…", "Verificando permissões…", "正在检查权限…"],
  "Permissions are only needed on macOS.": ["Los permisos solo hacen falta en macOS.", "Les autorisations ne sont nécessaires que sur macOS.", "Berechtigungen braucht es nur unter macOS.", "As permissões só são necessárias no macOS.", "只有 macOS 需要权限。"],
  "see your screen (required)": ["ver tu pantalla (obligatorio)", "voir ton écran (requis)", "deinen Bildschirm sehen (nötig)", "ver sua tela (obrigatório)", "查看屏幕（必需）"],
  "move the mouse and type (required)": ["mover el ratón y escribir (obligatorio)", "bouger la souris et taper (requis)", "Maus bewegen und tippen (nötig)", "mover o mouse e digitar (obrigatório)", "移动鼠标和打字（必需）"],
  "hear “Hey Agent”": ["oír “Hey Agent”", "entendre « Hey Agent »", "„Hey Agent“ hören", "ouvir “Hey Agent”", "听到“Hey Agent”"],
  "understand speech on this Mac": ["entender la voz en este Mac", "comprendre la voix sur ce Mac", "Sprache auf diesem Mac verstehen", "entender a fala neste Mac", "在本机上识别语音"],
  "record your demonstrations in teach mode": ["grabar tus demostraciones en el modo enseñar", "enregistrer tes démonstrations en mode apprentissage", "deine Vorführungen im Lernmodus aufnehmen", "gravar suas demonstrações no modo ensinar", "在教学模式中录制你的演示"],
  "open and switch apps": ["abrir y cambiar de app", "ouvrir et changer d'app", "Apps öffnen und wechseln", "abrir e alternar apps", "打开和切换应用"],
  "{label} was taken back. macOS asks again the next time Deskwright needs it.": [
    "Se retiró {label}. macOS volverá a preguntar la próxima vez que Deskwright lo necesite.",
    "{label} a été retiré. macOS redemandera la prochaine fois que Deskwright en aura besoin.",
    "{label} wurde entzogen. macOS fragt erneut, wenn Deskwright es das nächste Mal braucht.",
    "{label} foi revogado. O macOS pergunta de novo quando o Deskwright precisar.",
    "已收回{label}。下次 Deskwright 需要时 macOS 会再次询问。",
  ],
  "Couldn't change {label}; use System Settings.": ["No se pudo cambiar {label}; usa Ajustes del Sistema.", "Impossible de modifier {label} ; utilise Réglages Système.", "{label} ließ sich nicht ändern; nutze die Systemeinstellungen.", "Não foi possível alterar {label}; use os Ajustes do Sistema.", "无法更改{label}，请使用系统设置。"],
  "What macOS lets Deskwright do. Changes to Screen Recording and Accessibility apply after a restart.": [
    "Lo que macOS permite hacer a Deskwright. Los cambios en Grabación de pantalla y Accesibilidad se aplican tras reiniciar.",
    "Ce que macOS autorise Deskwright à faire. Les changements d'Enregistrement de l'écran et d'Accessibilité s'appliquent après un redémarrage.",
    "Was macOS Deskwright erlaubt. Änderungen an Bildschirmaufnahme und Bedienungshilfen gelten nach einem Neustart.",
    "O que o macOS permite que o Deskwright faça. Mudanças em Gravação de tela e Acessibilidade valem após reiniciar.",
    "macOS 允许 Deskwright 做的事。录屏和辅助功能的更改在重启后生效。",
  ],
  "Allowed": ["Permitido", "Autorisé", "Erlaubt", "Permitido", "已允许"],
  "Not allowed": ["No permitido", "Non autorisé", "Nicht erlaubt", "Não permitido", "未允许"],
  "Not asked yet": ["Aún no solicitado", "Pas encore demandé", "Noch nicht gefragt", "Ainda não solicitado", "尚未请求"],
  "Revoke": ["Revocar", "Retirer", "Entziehen", "Revogar", "撤销"],
  "Allow": ["Permitir", "Autoriser", "Erlauben", "Permitir", "允许"],
  "Speaking out loud and playing sound need no permission on macOS.": [
    "Hablar en voz alta y reproducir sonido no necesitan permiso en macOS.",
    "Parler à voix haute et jouer du son ne demandent aucune autorisation sur macOS.",
    "Laut sprechen und Ton abspielen brauchen unter macOS keine Berechtigung.",
    "Falar em voz alta e tocar som não precisam de permissão no macOS.",
    "在 macOS 上朗读和播放声音无需权限。",
  ],
  "The voice speaks this language. Voice commands work in it and in English.": [
    "La voz habla este idioma. Los comandos de voz funcionan en él y en inglés.",
    "La voix parle cette langue. Les commandes vocales fonctionnent dans cette langue et en anglais.",
    "Die Stimme spricht diese Sprache. Sprachbefehle funktionieren darin und auf Englisch.",
    "A voz fala este idioma. Os comandos de voz funcionam nele e em inglês.",
    "语音会用这种语言说话。语音指令支持这种语言和英语。",
  ],

  // Run statuses from the engine (tStatus)
  "Writing the script…": ["Escribiendo el programa…", "Écriture du programme…", "Schreibe das Programm…", "Escrevendo o programa…", "正在编写程序…"],
  "Fixing script problems…": ["Corrigiendo el programa…", "Correction du programme…", "Korrigiere das Programm…", "Corrigindo o programa…", "正在修复程序问题…"],
  "Fixing line {x}…": ["Arreglando la línea {x}…", "Correction de la ligne {x}…", "Korrigiere Zeile {x}…", "Corrigindo a linha {x}…", "正在修复第 {x} 行…"],
  "Opening app: {x}": ["Abriendo la app: {x}", "Ouverture de l'app : {x}", "Öffne App: {x}", "Abrindo o app: {x}", "正在打开应用：{x}"],
  "Opening {x}": ["Abriendo {x}", "Ouverture de {x}", "Öffne {x}", "Abrindo {x}", "正在打开 {x}"],
  "Looking at {x}": ["Mirando {x}", "Je regarde {x}", "Schaue auf {x}", "Olhando {x}", "正在查看 {x}"],
  "Looking for {x}": ["Buscando {x}", "Je cherche {x}", "Suche {x}", "Procurando {x}", "正在查找 {x}"],
  "Click {x}": ["Clic en {x}", "Clic sur {x}", "Klick auf {x}", "Clique em {x}", "点击 {x}"],
  "Double-click {x}": ["Doble clic en {x}", "Double-clic sur {x}", "Doppelklick auf {x}", "Clique duplo em {x}", "双击 {x}"],
  "Right-click {x}": ["Clic derecho en {x}", "Clic droit sur {x}", "Rechtsklick auf {x}", "Clique direito em {x}", "右键点击 {x}"],
  "Type into {x}": ["Escribir en {x}", "Saisie dans {x}", "Tippe in {x}", "Digitar em {x}", "在 {x} 中输入"],
  "Hover over {x}": ["Pasar sobre {x}", "Survol de {x}", "Zeige auf {x}", "Passar sobre {x}", "悬停在 {x}"],
  "Drag {x}": ["Arrastrar {x}", "Glisser {x}", "Ziehe {x}", "Arrastar {x}", "拖动 {x}"],
  "Typing: {x}": ["Escribiendo: {x}", "Saisie : {x}", "Tippe: {x}", "Digitando: {x}", "正在输入：{x}"],
  "Waiting for: {x}": ["Esperando: {x}", "En attente : {x}", "Warte auf: {x}", "Aguardando: {x}", "等待：{x}"],
  "Waiting {x}": ["Esperando {x}", "Attente {x}", "Warte {x}", "Aguardando {x}", "等待 {x}"],
  "Checking: {x}": ["Comprobando: {x}", "Vérification : {x}", "Prüfe: {x}", "Verificando: {x}", "检查：{x}"],
  "Asking: {x}": ["Preguntando: {x}", "Question : {x}", "Frage: {x}", "Perguntando: {x}", "询问：{x}"],
  "Reading: {x}": ["Leyendo: {x}", "Lecture : {x}", "Lese: {x}", "Lendo: {x}", "读取：{x}"],
  "Reading table: {x}": ["Leyendo la tabla: {x}", "Lecture du tableau : {x}", "Lese Tabelle: {x}", "Lendo a tabela: {x}", "读取表格：{x}"],
  "Scrolling down": ["Desplazando hacia abajo", "Défilement vers le bas", "Scrolle nach unten", "Rolando para baixo", "向下滚动"],
  "Scrolling up": ["Desplazando hacia arriba", "Défilement vers le haut", "Scrolle nach oben", "Rolando para cima", "向上滚动"],
  "Pressing: {x}": ["Pulsando: {x}", "Touche : {x}", "Drücke: {x}", "Pressionando: {x}", "按键：{x}"],
  "Shortcut: {x}": ["Atajo: {x}", "Raccourci : {x}", "Kurzbefehl: {x}", "Atalho: {x}", "快捷键：{x}"],
  "Menu: {x}": ["Menú: {x}", "Menu : {x}", "Menü: {x}", "Menu: {x}", "菜单：{x}"],
  "Focusing window: {x}": ["Activando la ventana: {x}", "Activation de la fenêtre : {x}", "Aktiviere Fenster: {x}", "Ativando a janela: {x}", "切换到窗口：{x}"],
  "Known way back: {x}": ["Camino de vuelta conocido: {x}", "Chemin de retour connu : {x}", "Bekannter Rückweg: {x}", "Caminho de volta conhecido: {x}", "已知返回路径：{x}"],
  "Summarizing: {x}": ["Resumiendo: {x}", "Résumé : {x}", "Fasse zusammen: {x}", "Resumindo: {x}", "总结：{x}"],
  "Waiting for confirmation": ["Esperando confirmación", "En attente de confirmation", "Warte auf Bestätigung", "Aguardando confirmação", "等待确认"],
  "Waiting for confirmation: {x}": ["Esperando confirmación: {x}", "En attente de confirmation : {x}", "Warte auf Bestätigung: {x}", "Aguardando confirmação: {x}", "等待确认：{x}"],
  "Waiting for your answer: {x}": ["Esperando tu respuesta: {x}", "En attente de ta réponse : {x}", "Warte auf deine Antwort: {x}", "Aguardando sua resposta: {x}", "等待你的回答：{x}"],
  "Running JavaScript in the page": ["Ejecutando JavaScript en la página", "Exécution de JavaScript dans la page", "Führe JavaScript auf der Seite aus", "Executando JavaScript na página", "正在页面中运行 JavaScript"],
  "Stopping…": ["Deteniendo…", "Arrêt…", "Stoppe…", "Parando…", "正在停止…"],
};

let current: Lang = "en";

export function setLang(code: string) {
  current = (LANGUAGES.some((l) => l.code === code) ? code : "en") as Lang;
}

export function getLang(): Lang {
  return current;
}

export function t(text: string, vars?: Record<string, string | number>): string {
  const row = current === "en" ? undefined : D[text];
  let out = row ? row[ORDER.indexOf(current)] : text;
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

/** n with the right singular/plural message: plural("1 run", "{n} runs", 3). */
export function plural(one: string, many: string, n: number): string {
  return n === 1 ? t(one) : t(many, { n });
}

// Engine statuses: a fixed prefix and the variable rest (a target, a key, an app name).
const STATUS: [RegExp, string][] = [
  [/^Fixing line (.+)…$/, "Fixing line {x}…"],
  [/^Opening app: (.+)$/, "Opening app: {x}"],
  [/^Looking at (.+)$/, "Looking at {x}"],
  [/^Looking for (.+)$/, "Looking for {x}"],
  [/^Double-click (.+)$/, "Double-click {x}"],
  [/^Right-click (.+)$/, "Right-click {x}"],
  [/^Click (.+)$/, "Click {x}"],
  [/^Type into (.+)$/, "Type into {x}"],
  [/^Hover over (.+)$/, "Hover over {x}"],
  [/^Drag (.+)$/, "Drag {x}"],
  [/^Typing: (.*)$/, "Typing: {x}"],
  [/^Waiting for confirmation: (.+)$/, "Waiting for confirmation: {x}"],
  [/^Waiting for your answer: (.+)$/, "Waiting for your answer: {x}"],
  [/^Waiting for: (.+)$/, "Waiting for: {x}"],
  [/^Waiting (\d.*)$/, "Waiting {x}"],
  [/^Checking: (.+)$/, "Checking: {x}"],
  [/^Asking: (.+)$/, "Asking: {x}"],
  [/^Reading table: (.+)$/, "Reading table: {x}"],
  [/^Reading: (.+)$/, "Reading: {x}"],
  [/^Pressing: (.+)$/, "Pressing: {x}"],
  [/^Shortcut: (.+)$/, "Shortcut: {x}"],
  [/^Menu: (.+)$/, "Menu: {x}"],
  [/^Focusing window: (.+)$/, "Focusing window: {x}"],
  [/^Known way back: (.+)$/, "Known way back: {x}"],
  [/^Summarizing: (.+)$/, "Summarizing: {x}"],
  [/^Opening (.+)$/, "Opening {x}"],
];

export function tStatus(text: string): string {
  if (current === "en" || !text) return text;
  if (D[text]) return t(text);
  for (const [re, key] of STATUS) {
    const m = text.match(re);
    if (m) return t(key, { x: m[1] });
  }
  return text;
}
