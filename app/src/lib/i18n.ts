// The app's text in Deskwright's languages. t("English text", { n: 3 }) returns it in the current language; the
// English text is the key, so a string without a translation shows in English. The engine localizes what it says
// (engine/i18n.py); run statuses it sends are translated here by their prefix (tStatus).

export type Lang = "en" | "es" | "fr" | "de" | "pt";

export const LANGUAGES: { code: Lang; name: string; english: string }[] = [
  { code: "en", name: "English", english: "English" },
  { code: "es", name: "Español", english: "Spanish" },
  { code: "fr", name: "Français", english: "French" },
  { code: "de", name: "Deutsch", english: "German" },
  { code: "pt", name: "Português", english: "Portuguese" },
];

const ORDER: Lang[] = ["es", "fr", "de", "pt"];

// English -> [Spanish, French, German, Portuguese]
const D: Record<string, [string, string, string, string]> = {
  // Header, menu, empty state
  "Language": ["Idioma", "Langue", "Sprache", "Idioma"],
  "Engine offline": ["Motor desconectado", "Moteur hors ligne", "Engine offline", "Motor offline"],
  "Connecting…": ["Conectando…", "Connexion…", "Verbinde…", "Conectando…"],
  "Sensitive actions run without asking. Click to turn approvals back on.": [
    "Las acciones sensibles se ejecutan sin preguntar. Haz clic para volver a activar las aprobaciones.",
    "Les actions sensibles s'exécutent sans demander. Clique pour réactiver les validations.",
    "Heikle Aktionen laufen ohne Rückfrage. Klicke, um Freigaben wieder einzuschalten.",
    "Ações sensíveis são executadas sem perguntar. Clique para reativar as aprovações.",
  ],
  "Approvals off": ["Aprobaciones desactivadas", "Validations désactivées", "Freigaben aus", "Aprovações desligadas"],
  "Working": ["Trabajando", "En cours", "Arbeitet", "Trabalhando"],
  "New conversation": ["Nueva conversación", "Nouvelle conversation", "Neue Unterhaltung", "Nova conversa"],
  "More": ["Más", "Plus", "Mehr", "Mais"],
  "Collapse": ["Contraer", "Réduire", "Einklappen", "Recolher"],
  "Finish demonstration": ["Terminar demostración", "Terminer la démonstration", "Vorführung beenden", "Concluir demonstração"],
  "Teach by demonstration": ["Enseñar con una demostración", "Apprendre par démonstration", "Durch Vorführen beibringen", "Ensinar por demonstração"],
  "Saved tasks": ["Tareas guardadas", "Tâches enregistrées", "Gespeicherte Aufgaben", "Tarefas salvas"],
  "Run metrics": ["Métricas de ejecución", "Statistiques d'exécution", "Laufstatistik", "Métricas de execução"],
  "Permissions": ["Permisos", "Autorisations", "Berechtigungen", "Permissões"],
  "Listen for “Hey Agent”": ["Escuchar “Hey Agent”", "Écouter « Hey Agent »", "Auf „Hey Agent“ hören", "Ouvir “Hey Agent”"],
  "Stop listening for “Hey Agent”": ["Dejar de escuchar “Hey Agent”", "Ne plus écouter « Hey Agent »", "Nicht mehr auf „Hey Agent“ hören", "Parar de ouvir “Hey Agent”"],
  "Speak out loud": ["Hablar en voz alta", "Parler à voix haute", "Laut sprechen", "Falar em voz alta"],
  "Speak out loud (loading voice…)": ["Hablar en voz alta (cargando voz…)", "Parler à voix haute (chargement de la voix…)", "Laut sprechen (Stimme lädt…)", "Falar em voz alta (carregando voz…)"],
  "Review before running": ["Revisar antes de ejecutar", "Vérifier avant d'exécuter", "Vor dem Ausführen prüfen", "Revisar antes de executar"],
  "Skip approvals": ["Omitir aprobaciones", "Ignorer les validations", "Freigaben überspringen", "Pular aprovações"],
  "Quit Deskwright": ["Salir de Deskwright", "Quitter Deskwright", "Deskwright beenden", "Sair do Deskwright"],
  "What should I do?": ["¿Qué hago?", "Que dois-je faire ?", "Was soll ich tun?", "O que devo fazer?"],
  "Describe a task and I'll take control.": ["Describe una tarea y tomaré el control.", "Décris une tâche et je prends le contrôle.", "Beschreib eine Aufgabe und ich übernehme.", "Descreva uma tarefa e eu assumo o controle."],
  "Thinking…": ["Pensando…", "Réflexion…", "Denke nach…", "Pensando…"],
  "Analysing your demonstration": ["Analizando tu demostración", "Analyse de ta démonstration", "Analysiere deine Vorführung", "Analisando sua demonstração"],
  "Close": ["Cerrar", "Fermer", "Schließen", "Fechar"],

  // Run narration in the chat
  "Running your saved task.": ["Ejecutando tu tarea guardada.", "J'exécute ta tâche enregistrée.", "Deine gespeicherte Aufgabe läuft.", "Executando sua tarefa salva."],
  "Ran your saved task.": ["Ejecuté tu tarea guardada.", "J'ai exécuté ta tâche enregistrée.", "Deine gespeicherte Aufgabe ist gelaufen.", "Executei sua tarefa salva."],
  "I wrote a program for this and I'm running it on your screen.": [
    "Escribí un programa para esto y lo estoy ejecutando en tu pantalla.",
    "J'ai écrit un programme pour ça et je l'exécute sur ton écran.",
    "Ich habe dafür ein Programm geschrieben und führe es auf deinem Bildschirm aus.",
    "Escrevi um programa para isso e estou executando na sua tela.",
  ],
  "Here's the program I wrote and ran.": ["Este es el programa que escribí y ejecuté.", "Voici le programme que j'ai écrit et exécuté.", "Hier ist das Programm, das ich geschrieben und ausgeführt habe.", "Aqui está o programa que escrevi e executei."],
  "Here's the program. Review it, then run it.": ["Aquí está el programa. Revísalo y luego ejecútalo.", "Voici le programme. Vérifie-le, puis exécute-le.", "Hier ist das Programm. Prüf es und führ es dann aus.", "Aqui está o programa. Revise e depois execute."],
  "Stage {i} of {n}": ["Etapa {i} de {n}", "Étape {i} sur {n}", "Schritt {i} von {n}", "Etapa {i} de {n}"],
  "Writing the program…": ["Escribiendo el programa…", "Écriture du programme…", "Schreibe das Programm…", "Escrevendo o programa…"],
  "Verified": ["Verificado", "Vérifié", "Bestätigt", "Verificado"],
  "Not verified": ["No verificado", "Non vérifié", "Nicht bestätigt", "Não verificado"],
  "Expected": ["Esperado", "Attendu", "Erwartet", "Esperado"],
  "Saw": ["Visto", "Vu", "Gesehen", "Visto"],
  "{a} of {b} records": ["{a} de {b} registros", "{a} sur {b} enregistrements", "{a} von {b} Einträgen", "{a} de {b} registros"],
  "1 fix": ["1 corrección", "1 correction", "1 Korrektur", "1 correção"],
  "{n} fixes": ["{n} correcciones", "{n} corrections", "{n} Korrekturen", "{n} correções"],
  "Edit": ["Editar", "Modifier", "Bearbeiten", "Editar"],
  "Copy": ["Copiar", "Copier", "Kopieren", "Copiar"],
  "Copied": ["Copiado", "Copié", "Kopiert", "Copiado"],
  "Took a learned way back to line {n}.": ["Tomé un camino aprendido de vuelta a la línea {n}.", "J'ai pris un chemin appris pour revenir à la ligne {n}.", "Bin über einen gelernten Weg zu Zeile {n} zurück.", "Usei um caminho aprendido de volta à linha {n}."],
  "Rewrote from line {n} and resumed.": ["Reescribí desde la línea {n} y continué.", "J'ai réécrit à partir de la ligne {n} et repris.", "Ab Zeile {n} neu geschrieben und fortgesetzt.", "Reescrevi a partir da linha {n} e continuei."],
  "1 line replaced by the rewrite below": ["1 línea reemplazada por la reescritura de abajo", "1 ligne remplacée par la réécriture ci-dessous", "1 Zeile durch die Neufassung unten ersetzt", "1 linha substituída pela reescrita abaixo"],
  "{n} lines replaced by the rewrite below": ["{n} líneas reemplazadas por la reescritura de abajo", "{n} lignes remplacées par la réécriture ci-dessous", "{n} Zeilen durch die Neufassung unten ersetzt", "{n} linhas substituídas pela reescrita abaixo"],
  "Name this task": ["Ponle nombre a esta tarea", "Nomme cette tâche", "Aufgabe benennen", "Dê um nome a esta tarefa"],
  "Save": ["Guardar", "Enregistrer", "Speichern", "Salvar"],
  "Cancel": ["Cancelar", "Annuler", "Abbrechen", "Cancelar"],
  "Run": ["Ejecutar", "Exécuter", "Ausführen", "Executar"],
  "Teach": ["Enseñar", "Montrer", "Beibringen", "Ensinar"],
  "Save as task": ["Guardar como tarea", "Enregistrer comme tâche", "Als Aufgabe speichern", "Salvar como tarefa"],
  "or say “start”": ["o di “empieza”", "ou dis « commence »", "oder sag „start“", "ou diga “começar”"],

  // Cards
  "Show in Finder": ["Mostrar en Finder", "Afficher dans le Finder", "Im Finder zeigen", "Mostrar no Finder"],
  "You answered: {a}": ["Respondiste: {a}", "Tu as répondu : {a}", "Deine Antwort: {a}", "Você respondeu: {a}"],
  "No longer needed": ["Ya no es necesario", "Plus nécessaire", "Nicht mehr nötig", "Não é mais necessário"],
  "Reply…": ["Responder…", "Répondre…", "Antworten…", "Responder…"],
  "Approved": ["Aprobado", "Validé", "Freigegeben", "Aprovado"],
  "Declined": ["Rechazado", "Refusé", "Abgelehnt", "Recusado"],
  "Closed": ["Cerrado", "Fermé", "Geschlossen", "Fechado"],
  "Approve this action?": ["¿Apruebas esta acción?", "Valider cette action ?", "Diese Aktion freigeben?", "Aprovar esta ação?"],
  "Approve": ["Aprobar", "Valider", "Freigeben", "Aprovar"],
  "Decline": ["Rechazar", "Refuser", "Ablehnen", "Recusar"],
  "Approve all this run": ["Aprobar todo en esta ejecución", "Tout valider pour cette exécution", "Alles in diesem Lauf freigeben", "Aprovar tudo nesta execução"],
  "Done in {s}s": ["Listo en {s} s", "Terminé en {s} s", "Fertig in {s} s", "Concluído em {s} s"],
  "Stopped": ["Detenido", "Arrêté", "Gestoppt", "Parado"],
  "Stopped: you declined an action": ["Detenido: rechazaste una acción", "Arrêté : tu as refusé une action", "Gestoppt: du hast eine Aktion abgelehnt", "Parado: você recusou uma ação"],
  "Couldn't finish": ["No se pudo terminar", "Impossible de terminer", "Nicht abgeschlossen", "Não foi possível concluir"],
  "Save as a reusable task": ["Guardar como tarea reutilizable", "Enregistrer comme tâche réutilisable", "Als wiederverwendbare Aufgabe speichern", "Salvar como tarefa reutilizável"],
  "Continue after “{name}”": ["Continuar después de “{name}”", "Reprendre après « {name} »", "Nach „{name}“ fortsetzen", "Continuar depois de “{name}”"],
  "{n} steps": ["{n} pasos", "{n} étapes", "{n} Schritte", "{n} passos"],
  "{n} model calls": ["{n} llamadas al modelo", "{n} appels au modèle", "{n} Modellaufrufe", "{n} chamadas ao modelo"],
  "{n}% from cache": ["{n}% desde la caché", "{n} % depuis le cache", "{n} % aus dem Cache", "{n}% do cache"],
  "{a}/{b} self-fixes worked": ["{a}/{b} autocorrecciones funcionaron", "{a}/{b} auto-corrections ont fonctionné", "{a}/{b} Selbstkorrekturen haben geklappt", "{a}/{b} autocorreções funcionaram"],
  "Run {n}: {x}× faster than run 1": ["Ejecución {n}: {x}× más rápida que la 1", "Exécution {n} : {x}× plus rapide que la 1", "Lauf {n}: {x}× schneller als Lauf 1", "Execução {n}: {x}× mais rápida que a 1"],
  "Run {n}: {x}× faster, {p}% cheaper than run 1": ["Ejecución {n}: {x}× más rápida y {p}% más barata que la 1", "Exécution {n} : {x}× plus rapide et {p} % moins chère que la 1", "Lauf {n}: {x}× schneller und {p} % günstiger als Lauf 1", "Execução {n}: {x}× mais rápida e {p}% mais barata que a 1"],
  "The position cache skipped {n} model calls (about {s}s, {c}).": [
    "La caché de posiciones evitó {n} llamadas al modelo (unos {s} s, {c}).",
    "Le cache de positions a évité {n} appels au modèle (environ {s} s, {c}).",
    "Der Positions-Cache hat {n} Modellaufrufe gespart (etwa {s} s, {c}).",
    "O cache de posições evitou {n} chamadas ao modelo (cerca de {s} s, {c}).",
  ],
  "Saved as “{name}”. Say “Agent, run {name}” any time.": [
    "Guardada como “{name}”. Di “Agente, ejecuta {name}” cuando quieras.",
    "Enregistrée sous « {name} ». Dis « Agent, lance {name} » quand tu veux.",
    "Gespeichert als „{name}“. Sag jederzeit „Agent, führe {name} aus“.",
    "Salva como “{name}”. Diga “Agente, execute {name}” quando quiser.",
  ],
  "No elements were looked up on screen in this run.": [
    "En esta ejecución no se buscó ningún elemento en pantalla.",
    "Aucun élément n'a été cherché à l'écran pendant cette exécution.",
    "In diesem Lauf wurde nichts auf dem Bildschirm gesucht.",
    "Nenhum elemento foi procurado na tela nesta execução.",
  ],
  "Position cache cleared": ["Caché de posiciones borrada", "Cache de positions vidé", "Positions-Cache geleert", "Cache de posições limpo"],
  "Cost per day": ["Coste por día", "Coût par jour", "Kosten pro Tag", "Custo por dia"],
  "Runs and model calls per day": ["Ejecuciones y llamadas al modelo por día", "Exécutions et appels au modèle par jour", "Läufe und Modellaufrufe pro Tag", "Execuções e chamadas ao modelo por dia"],
  "Runs": ["Ejecuciones", "Exécutions", "Läufe", "Execuções"],
  "Average run time: first run vs. repeats": ["Tiempo medio: primera ejecución frente a repeticiones", "Durée moyenne : première exécution et répétitions", "Durchschnittliche Laufzeit: erster Lauf und Wiederholungen", "Tempo médio: primeira execução x repetições"],
  "A repeat is a saved task or the same request run again: the position cache makes it faster.": [
    "Una repetición es una tarea guardada o la misma petición otra vez: la caché de posiciones la acelera.",
    "Une répétition est une tâche enregistrée ou la même demande relancée : le cache de positions l'accélère.",
    "Eine Wiederholung ist eine gespeicherte Aufgabe oder dieselbe Anfrage noch einmal: der Positions-Cache beschleunigt sie.",
    "Uma repetição é uma tarefa salva ou o mesmo pedido de novo: o cache de posições a deixa mais rápida.",
  ],
  "First run": ["Primera ejecución", "Première exécution", "Erster Lauf", "Primeira execução"],
  "Repeat": ["Repetición", "Répétition", "Wiederholung", "Repetição"],
  "Copy code": ["Copiar código", "Copier le code", "Code kopieren", "Copiar código"],
  "I watched your demonstration ({n} steps) and turned it into a program. Recorded values became variables, so it can run on new records.": [
    "Vi tu demostración ({n} pasos) y la convertí en un programa. Los valores grabados son variables, así que puede usarse con registros nuevos.",
    "J'ai regardé ta démonstration ({n} étapes) et l'ai transformée en programme. Les valeurs enregistrées sont devenues des variables, il peut donc traiter de nouveaux enregistrements.",
    "Ich habe deine Vorführung ({n} Schritte) angesehen und in ein Programm verwandelt. Aufgezeichnete Werte wurden zu Variablen, also läuft es auch mit neuen Einträgen.",
    "Assisti à sua demonstração ({n} passos) e transformei em um programa. Os valores gravados viraram variáveis, então ele funciona com novos registros.",
  ],
  "and {n} more": ["y {n} más", "et {n} de plus", "und {n} weitere", "e mais {n}"],
  "Needs a quick edit: {p}": ["Necesita un pequeño ajuste: {p}", "Une petite retouche est nécessaire : {p}", "Braucht eine kleine Änderung: {p}", "Precisa de um pequeno ajuste: {p}"],

  // Composer
  "Show saved tasks": ["Mostrar tareas guardadas", "Afficher les tâches enregistrées", "Gespeicherte Aufgaben zeigen", "Mostrar tarefas salvas"],
  "Show run metrics": ["Mostrar métricas", "Afficher les statistiques", "Laufstatistik zeigen", "Mostrar métricas"],
  "Run scripts right away": ["Ejecutar los programas al momento", "Exécuter les programmes tout de suite", "Programme sofort ausführen", "Executar os programas na hora"],
  "Clear the conversation": ["Borrar la conversación", "Effacer la conversation", "Unterhaltung löschen", "Limpar a conversa"],
  "Working on it…": ["Trabajando en ello…", "Je m'en occupe…", "Bin dran…", "Trabalhando nisso…"],
  "Say “Agent…” or type a task": ["Di “Agente…” o escribe una tarea", "Dis « Agent… » ou tape une tâche", "Sag „Agent…“ oder tippe eine Aufgabe", "Diga “Agente…” ou digite uma tarefa"],
  "Ask Agent to do something": ["Pídele algo a Deskwright", "Demande quelque chose à Deskwright", "Bitte Deskwright um etwas", "Peça algo ao Deskwright"],
  "Recording your demonstration · {t}": ["Grabando tu demostración · {t}", "Enregistrement de ta démonstration · {t}", "Deine Vorführung wird aufgenommen · {t}", "Gravando sua demonstração · {t}"],
  "Do the task once in any app.": ["Haz la tarea una vez en cualquier app.", "Fais la tâche une fois dans n'importe quelle app.", "Mach die Aufgabe einmal in einer beliebigen App.", "Faça a tarefa uma vez em qualquer app."],
  "Finish": ["Terminar", "Terminer", "Fertig", "Concluir"],
  "Cancel (esc)": ["Cancelar (esc)", "Annuler (esc)", "Abbrechen (esc)", "Cancelar (esc)"],
  "Send": ["Enviar", "Envoyer", "Senden", "Enviar"],
  "Press esc or say “stop” to stop": ["Pulsa esc o di “para” para detener", "Appuie sur esc ou dis « stop » pour arrêter", "Drück esc oder sag „stopp“ zum Anhalten", "Pressione esc ou diga “pare” para parar"],
  "Press esc to stop": ["Pulsa esc para detener", "Appuie sur esc pour arrêter", "Drück esc zum Anhalten", "Pressione esc para parar"],
  "Approvals are off: sensitive actions run without asking.": ["Las aprobaciones están desactivadas: las acciones sensibles se ejecutan sin preguntar.", "Les validations sont désactivées : les actions sensibles s'exécutent sans demander.", "Freigaben sind aus: heikle Aktionen laufen ohne Rückfrage.", "As aprovações estão desligadas: ações sensíveis rodam sem perguntar."],

  // Corner bar
  "Open panel": ["Abrir panel", "Ouvrir le panneau", "Panel öffnen", "Abrir painel"],
  "Open panel (connecting…)": ["Abrir panel (conectando…)", "Ouvrir le panneau (connexion…)", "Panel öffnen (verbinde…)", "Abrir painel (conectando…)"],
  "Working…": ["Trabajando…", "En cours…", "Arbeitet…", "Trabalhando…"],
  "Press": ["Pulsa", "Appuie sur", "Drück", "Pressione"],
  "to stop": ["para detener", "pour arrêter", "zum Anhalten", "para parar"],
  "or say “stop” to stop": ["o di “para” para detener", "ou dis « stop » pour arrêter", "oder sag „stopp“ zum Anhalten", "ou diga “pare” para parar"],
  "{n} cached": ["{n} en caché", "{n} en cache", "{n} aus dem Cache", "{n} em cache"],
  "{n} calls": ["{n} llamadas", "{n} appels", "{n} Aufrufe", "{n} chamadas"],
  "Listening: say “stop” to stop": ["Escuchando: di “para” para detener", "À l'écoute : dis « stop » pour arrêter", "Hört zu: sag „stopp“ zum Anhalten", "Ouvindo: diga “pare” para parar"],

  // Results
  "Export": ["Exportar", "Exporter", "Exportieren", "Exportar"],
  "Copy to clipboard": ["Copiar al portapapeles", "Copier dans le presse-papiers", "In die Zwischenablage", "Copiar para a área de transferência"],
  "Table": ["Tabla", "Tableau", "Tabelle", "Tabela"],
  "1 row": ["1 fila", "1 ligne", "1 Zeile", "1 linha"],
  "{n} rows": ["{n} filas", "{n} lignes", "{n} Zeilen", "{n} linhas"],
  "From the position cache": ["Desde la caché de posiciones", "Depuis le cache de positions", "Aus dem Positions-Cache", "Do cache de posições"],
  "Found by the vision models": ["Encontrado por los modelos de visión", "Trouvé par les modèles de vision", "Von den Bildmodellen gefunden", "Encontrado pelos modelos de visão"],
  "Copied to the clipboard": ["Copiado al portapapeles", "Copié dans le presse-papiers", "In die Zwischenablage kopiert", "Copiado para a área de transferência"],
  "Exported the task's code (run it from other apps with deskwright.py)": [
    "Exporté el código de la tarea (ejecútalo desde otras apps con deskwright.py)",
    "Code de la tâche exporté (lance-le depuis d'autres apps avec deskwright.py)",
    "Code der Aufgabe exportiert (aus anderen Apps mit deskwright.py ausführen)",
    "Código da tarefa exportado (execute em outros apps com deskwright.py)",
  ],
  "Exported {f}": ["Exportado {f}", "{f} exporté", "{f} exportiert", "{f} exportado"],

  // Saved tasks and metrics
  "No saved tasks yet. Save a finished run, or teach me one: open the … menu and choose": [
    "Aún no hay tareas guardadas. Guarda una ejecución terminada o enséñame una: abre el menú … y elige",
    "Aucune tâche enregistrée. Enregistre une exécution terminée ou apprends-m'en une : ouvre le menu … et choisis",
    "Noch keine gespeicherten Aufgaben. Speichere einen fertigen Lauf oder bring mir eine bei: öffne das Menü … und wähle",
    "Nenhuma tarefa salva ainda. Salve uma execução concluída ou me ensine uma: abra o menu … e escolha",
  ],
  "1 run": ["1 ejecución", "1 exécution", "1 Lauf", "1 execução"],
  "{n} runs": ["{n} ejecuciones", "{n} exécutions", "{n} Läufe", "{n} execuções"],
  "1 way back learned": ["1 camino de vuelta aprendido", "1 chemin de retour appris", "1 Rückweg gelernt", "1 caminho de volta aprendido"],
  "{n} ways back learned": ["{n} caminos de vuelta aprendidos", "{n} chemins de retour appris", "{n} Rückwege gelernt", "{n} caminhos de volta aprendidos"],
  "now {x}× faster": ["ahora {x}× más rápida", "désormais {x}× plus rapide", "jetzt {x}× schneller", "agora {x}× mais rápida"],
  "time": ["tiempo", "temps", "Zeit", "tempo"],
  "cost": ["coste", "coût", "Kosten", "custo"],
  "Latest: {note}": ["Última: {note}", "Dernière : {note}", "Neueste: {note}", "Mais recente: {note}"],
  "Original version": ["Versión original", "Version d'origine", "Ursprüngliche Version", "Versão original"],
  "Export code": ["Exportar código", "Exporter le code", "Code exportieren", "Exportar código"],
  "Delete": ["Eliminar", "Supprimer", "Löschen", "Excluir"],
  "Here's how the last run went.": ["Así fue la última ejecución.", "Voici comment s'est passée la dernière exécution.", "So lief der letzte Lauf.", "Veja como foi a última execução."],
  "No runs yet this session.": ["Todavía no hay ejecuciones en esta sesión.", "Aucune exécution pour l'instant.", "In dieser Sitzung noch keine Läufe.", "Nenhuma execução nesta sessão ainda."],
  "Time": ["Tiempo", "Temps", "Zeit", "Tempo"],
  "{s}s in models": ["{s} s en modelos", "{s} s dans les modèles", "{s} s in Modellen", "{s} s nos modelos"],
  "Cost": ["Coste", "Coût", "Kosten", "Custo"],
  "Steps": ["Pasos", "Étapes", "Schritte", "Passos"],
  "Model calls": ["Llamadas al modelo", "Appels au modèle", "Modellaufrufe", "Chamadas ao modelo"],
  "From cache": ["Desde caché", "Depuis le cache", "Aus dem Cache", "Do cache"],
  "{n} calls skipped": ["{n} llamadas evitadas", "{n} appels évités", "{n} Aufrufe gespart", "{n} chamadas evitadas"],
  "Self-fixes": ["Autocorrecciones", "Auto-corrections", "Selbstkorrekturen", "Autocorreções"],
  "worked / tried": ["funcionaron / intentadas", "réussies / tentées", "geklappt / versucht", "funcionaram / tentadas"],
  "Across all {n} runs: {a}% succeeded, and {b}% of self-fixes worked.": [
    "En las {n} ejecuciones: {a}% salieron bien y {b}% de las autocorrecciones funcionaron.",
    "Sur les {n} exécutions : {a} % ont réussi et {b} % des auto-corrections ont fonctionné.",
    "Über alle {n} Läufe: {a} % erfolgreich, {b} % der Selbstkorrekturen haben geklappt.",
    "Em todas as {n} execuções: {a}% deram certo e {b}% das autocorreções funcionaram.",
  ],
  "Clear the position cache": ["Borrar la caché de posiciones", "Vider le cache de positions", "Positions-Cache leeren", "Limpar o cache de posições"],
  "No runs yet": ["Aún no hay ejecuciones", "Aucune exécution", "Noch keine Läufe", "Nenhuma execução ainda"],

  // Permissions
  "Screen Recording": ["Grabación de pantalla", "Enregistrement de l'écran", "Bildschirmaufnahme", "Gravação de tela"],
  "Accessibility": ["Accesibilidad", "Accessibilité", "Bedienungshilfen", "Acessibilidade"],
  "Microphone": ["Micrófono", "Micro", "Mikrofon", "Microfone"],
  "Input Monitoring": ["Monitorización de entrada", "Surveillance de l'entrée", "Eingabeüberwachung", "Monitoramento de entrada"],
  "Speech Recognition": ["Reconocimiento de voz", "Reconnaissance vocale", "Spracherkennung", "Reconhecimento de fala"],
  "Automation": ["Automatización", "Automatisation", "Automation", "Automação"],
  "to see your screen": ["para ver tu pantalla", "pour voir ton écran", "um deinen Bildschirm zu sehen", "para ver sua tela"],
  "to move the mouse and type": ["para mover el ratón y escribir", "pour bouger la souris et taper", "um die Maus zu bewegen und zu tippen", "para mover o mouse e digitar"],
  "for voice, optional": ["para la voz, opcional", "pour la voix, facultatif", "für Sprache, optional", "para voz, opcional"],
  "for teach mode": ["para el modo enseñar", "pour le mode apprentissage", "für den Lernmodus", "para o modo ensinar"],
  "Before the first run": ["Antes de la primera ejecución", "Avant la première exécution", "Vor dem ersten Lauf", "Antes da primeira execução"],
  "macOS needs to allow this app to see and control the screen. Restart the app after granting.": [
    "macOS debe permitir que esta app vea y controle la pantalla. Reinicia la app después de darle permiso.",
    "macOS doit autoriser cette app à voir et contrôler l'écran. Redémarre l'app après l'autorisation.",
    "macOS muss dieser App erlauben, den Bildschirm zu sehen und zu steuern. Starte die App danach neu.",
    "O macOS precisa permitir que este app veja e controle a tela. Reinicie o app depois de permitir.",
  ],
  "Open": ["Abrir", "Ouvrir", "Öffnen", "Abrir"],
  "Screen Recording is on. macOS applies it after Deskwright restarts.": [
    "La grabación de pantalla está activada. macOS la aplica cuando Deskwright se reinicia.",
    "L'enregistrement de l'écran est activé. macOS l'applique après le redémarrage de Deskwright.",
    "Bildschirmaufnahme ist an. macOS übernimmt sie nach einem Neustart von Deskwright.",
    "A gravação de tela está ativada. O macOS aplica depois que o Deskwright reiniciar.",
  ],
  "Restart Deskwright": ["Reiniciar Deskwright", "Redémarrer Deskwright", "Deskwright neu starten", "Reiniciar o Deskwright"],
  "Tip: turn on Do Not Disturb so notifications stay out of screenshots.": [
    "Consejo: activa No molestar para que las notificaciones no salgan en las capturas.",
    "Astuce : active Ne pas déranger pour que les notifications n'apparaissent pas dans les captures.",
    "Tipp: Schalte „Nicht stören“ ein, damit Mitteilungen nicht in Bildschirmfotos landen.",
    "Dica: ative Não Perturbe para que as notificações não apareçam nas capturas.",
  ],
  "Done": ["Listo", "Terminé", "Fertig", "Pronto"],
  "Checking permissions…": ["Comprobando permisos…", "Vérification des autorisations…", "Prüfe Berechtigungen…", "Verificando permissões…"],
  "Permissions are only needed on macOS.": ["Los permisos solo hacen falta en macOS.", "Les autorisations ne sont nécessaires que sur macOS.", "Berechtigungen braucht es nur unter macOS.", "As permissões só são necessárias no macOS."],
  "see your screen (required)": ["ver tu pantalla (obligatorio)", "voir ton écran (requis)", "deinen Bildschirm sehen (nötig)", "ver sua tela (obrigatório)"],
  "move the mouse and type (required)": ["mover el ratón y escribir (obligatorio)", "bouger la souris et taper (requis)", "Maus bewegen und tippen (nötig)", "mover o mouse e digitar (obrigatório)"],
  "hear “Hey Agent”": ["oír “Hey Agent”", "entendre « Hey Agent »", "„Hey Agent“ hören", "ouvir “Hey Agent”"],
  "understand speech on this Mac": ["entender la voz en este Mac", "comprendre la voix sur ce Mac", "Sprache auf diesem Mac verstehen", "entender a fala neste Mac"],
  "record your demonstrations in teach mode": ["grabar tus demostraciones en el modo enseñar", "enregistrer tes démonstrations en mode apprentissage", "deine Vorführungen im Lernmodus aufnehmen", "gravar suas demonstrações no modo ensinar"],
  "open and switch apps": ["abrir y cambiar de app", "ouvrir et changer d'app", "Apps öffnen und wechseln", "abrir e alternar apps"],
  "{label} was taken back. macOS asks again the next time Deskwright needs it.": [
    "Se retiró {label}. macOS volverá a preguntar la próxima vez que Deskwright lo necesite.",
    "{label} a été retiré. macOS redemandera la prochaine fois que Deskwright en aura besoin.",
    "{label} wurde entzogen. macOS fragt erneut, wenn Deskwright es das nächste Mal braucht.",
    "{label} foi revogado. O macOS pergunta de novo quando o Deskwright precisar.",
  ],
  "Couldn't change {label}; use System Settings.": ["No se pudo cambiar {label}; usa Ajustes del Sistema.", "Impossible de modifier {label} ; utilise Réglages Système.", "{label} ließ sich nicht ändern; nutze die Systemeinstellungen.", "Não foi possível alterar {label}; use os Ajustes do Sistema."],
  "What macOS lets Deskwright do. Changes to Screen Recording and Accessibility apply after a restart.": [
    "Lo que macOS permite hacer a Deskwright. Los cambios en Grabación de pantalla y Accesibilidad se aplican tras reiniciar.",
    "Ce que macOS autorise Deskwright à faire. Les changements d'Enregistrement de l'écran et d'Accessibilité s'appliquent après un redémarrage.",
    "Was macOS Deskwright erlaubt. Änderungen an Bildschirmaufnahme und Bedienungshilfen gelten nach einem Neustart.",
    "O que o macOS permite que o Deskwright faça. Mudanças em Gravação de tela e Acessibilidade valem após reiniciar.",
  ],
  "Allowed": ["Permitido", "Autorisé", "Erlaubt", "Permitido"],
  "Not allowed": ["No permitido", "Non autorisé", "Nicht erlaubt", "Não permitido"],
  "Not asked yet": ["Aún no solicitado", "Pas encore demandé", "Noch nicht gefragt", "Ainda não solicitado"],
  "Revoke": ["Revocar", "Retirer", "Entziehen", "Revogar"],
  "Allow": ["Permitir", "Autoriser", "Erlauben", "Permitir"],
  "Speaking out loud and playing sound need no permission on macOS.": [
    "Hablar en voz alta y reproducir sonido no necesitan permiso en macOS.",
    "Parler à voix haute et jouer du son ne demandent aucune autorisation sur macOS.",
    "Laut sprechen und Ton abspielen brauchen unter macOS keine Berechtigung.",
    "Falar em voz alta e tocar som não precisam de permissão no macOS.",
  ],
  "The voice speaks this language. Voice commands work in it and in English.": [
    "La voz habla este idioma. Los comandos de voz funcionan en él y en inglés.",
    "La voix parle cette langue. Les commandes vocales fonctionnent dans cette langue et en anglais.",
    "Die Stimme spricht diese Sprache. Sprachbefehle funktionieren darin und auf Englisch.",
    "A voz fala este idioma. Os comandos de voz funcionam nele e em inglês.",
  ],

  // Run statuses from the engine (tStatus)
  "Writing the script…": ["Escribiendo el programa…", "Écriture du programme…", "Schreibe das Programm…", "Escrevendo o programa…"],
  "Fixing script problems…": ["Corrigiendo el programa…", "Correction du programme…", "Korrigiere das Programm…", "Corrigindo o programa…"],
  "Fixing line {x}…": ["Arreglando la línea {x}…", "Correction de la ligne {x}…", "Korrigiere Zeile {x}…", "Corrigindo a linha {x}…"],
  "Opening app: {x}": ["Abriendo la app: {x}", "Ouverture de l'app : {x}", "Öffne App: {x}", "Abrindo o app: {x}"],
  "Opening {x}": ["Abriendo {x}", "Ouverture de {x}", "Öffne {x}", "Abrindo {x}"],
  "Looking at {x}": ["Mirando {x}", "Je regarde {x}", "Schaue auf {x}", "Olhando {x}"],
  "Looking for {x}": ["Buscando {x}", "Je cherche {x}", "Suche {x}", "Procurando {x}"],
  "Click {x}": ["Clic en {x}", "Clic sur {x}", "Klick auf {x}", "Clique em {x}"],
  "Double-click {x}": ["Doble clic en {x}", "Double-clic sur {x}", "Doppelklick auf {x}", "Clique duplo em {x}"],
  "Right-click {x}": ["Clic derecho en {x}", "Clic droit sur {x}", "Rechtsklick auf {x}", "Clique direito em {x}"],
  "Type into {x}": ["Escribir en {x}", "Saisie dans {x}", "Tippe in {x}", "Digitar em {x}"],
  "Hover over {x}": ["Pasar sobre {x}", "Survol de {x}", "Zeige auf {x}", "Passar sobre {x}"],
  "Drag {x}": ["Arrastrar {x}", "Glisser {x}", "Ziehe {x}", "Arrastar {x}"],
  "Typing: {x}": ["Escribiendo: {x}", "Saisie : {x}", "Tippe: {x}", "Digitando: {x}"],
  "Waiting for: {x}": ["Esperando: {x}", "En attente : {x}", "Warte auf: {x}", "Aguardando: {x}"],
  "Waiting {x}": ["Esperando {x}", "Attente {x}", "Warte {x}", "Aguardando {x}"],
  "Checking: {x}": ["Comprobando: {x}", "Vérification : {x}", "Prüfe: {x}", "Verificando: {x}"],
  "Asking: {x}": ["Preguntando: {x}", "Question : {x}", "Frage: {x}", "Perguntando: {x}"],
  "Reading: {x}": ["Leyendo: {x}", "Lecture : {x}", "Lese: {x}", "Lendo: {x}"],
  "Reading table: {x}": ["Leyendo la tabla: {x}", "Lecture du tableau : {x}", "Lese Tabelle: {x}", "Lendo a tabela: {x}"],
  "Scrolling down": ["Desplazando hacia abajo", "Défilement vers le bas", "Scrolle nach unten", "Rolando para baixo"],
  "Scrolling up": ["Desplazando hacia arriba", "Défilement vers le haut", "Scrolle nach oben", "Rolando para cima"],
  "Pressing: {x}": ["Pulsando: {x}", "Touche : {x}", "Drücke: {x}", "Pressionando: {x}"],
  "Shortcut: {x}": ["Atajo: {x}", "Raccourci : {x}", "Kurzbefehl: {x}", "Atalho: {x}"],
  "Menu: {x}": ["Menú: {x}", "Menu : {x}", "Menü: {x}", "Menu: {x}"],
  "Focusing window: {x}": ["Activando la ventana: {x}", "Activation de la fenêtre : {x}", "Aktiviere Fenster: {x}", "Ativando a janela: {x}"],
  "Known way back: {x}": ["Camino de vuelta conocido: {x}", "Chemin de retour connu : {x}", "Bekannter Rückweg: {x}", "Caminho de volta conhecido: {x}"],
  "Summarizing: {x}": ["Resumiendo: {x}", "Résumé : {x}", "Fasse zusammen: {x}", "Resumindo: {x}"],
  "Waiting for confirmation": ["Esperando confirmación", "En attente de confirmation", "Warte auf Bestätigung", "Aguardando confirmação"],
  "Waiting for confirmation: {x}": ["Esperando confirmación: {x}", "En attente de confirmation : {x}", "Warte auf Bestätigung: {x}", "Aguardando confirmação: {x}"],
  "Waiting for your answer: {x}": ["Esperando tu respuesta: {x}", "En attente de ta réponse : {x}", "Warte auf deine Antwort: {x}", "Aguardando sua resposta: {x}"],
  "Running JavaScript in the page": ["Ejecutando JavaScript en la página", "Exécution de JavaScript dans la page", "Führe JavaScript auf der Seite aus", "Executando JavaScript na página"],
  "Stopping…": ["Deteniendo…", "Arrêt…", "Stoppe…", "Parando…"],
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
