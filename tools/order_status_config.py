"""Validazione della configurazione condivisa degli stati ordine."""
import re


def validate_status_config(payload, existing_codes, used_codes):
    rows = payload.get("statuses") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError("Inserisci da 1 a 50 stati.")
    result, codes, reactions = [], set(), set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Stato non valido.")
        code = row.get("code")
        label = row.get("label")
        reaction = row.get("slack_reaction") or ""
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,29}", code):
            raise ValueError("Codice: usa lettere minuscole, numeri e underscore (massimo 30 caratteri).")
        if code in codes:
            raise ValueError(f"Codice duplicato: {code}.")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 64:
            raise ValueError(f"Inserisci un nome valido per {code} (massimo 64 caratteri).")
        if not isinstance(reaction, str):
            raise ValueError(f"Reaction non valida per {code}.")
        reaction = reaction.strip().strip(":")
        if reaction and not re.fullmatch(r"[a-zA-Z0-9_+\-]{1,64}", reaction):
            raise ValueError(f"Per {code} usa il nome Slack della reaction, ad esempio truck o :truck:.")
        if reaction and reaction in reactions:
            raise ValueError(f"Reaction associata a piu' stati: {reaction}.")
        if type(row.get("is_visible")) is not bool or type(row.get("is_terminal")) is not bool:
            raise ValueError(f"Visibilita' e stato finale non validi per {code}.")
        if not row["is_visible"] and code in used_codes:
            raise ValueError(f"{code}: ci sono ordini in questo stato. Spostali prima di nascondere la colonna.")
        if code == "acquisito" and (not row["is_visible"] or row["is_terminal"]):
            raise ValueError("Acquisito e' lo stato iniziale dei nuovi ordini: deve restare visibile e non finale.")
        codes.add(code)
        if reaction:
            reactions.add(reaction)
        result.append(dict(code=code, label=label.strip(), slack_reaction=reaction or None,
                           order_index=index, is_visible=row["is_visible"], is_terminal=row["is_terminal"]))
    if not set(existing_codes).issubset(codes):
        raise ValueError("I codici esistenti non possono essere rimossi o rinominati; puoi cambiare il nome della colonna.")
    if not any(row["is_visible"] for row in result):
        raise ValueError("Mantieni almeno una colonna visibile.")
    return result
