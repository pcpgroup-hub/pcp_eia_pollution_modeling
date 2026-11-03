# -*- coding: utf-8 -*-
"""Load model cards (JSON) shipped with the plugin. No QGIS imports."""
import json
import os

CARDS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cards")


def list_cards(cards_dir=CARDS_DIR):
    return sorted(f[:-5] for f in os.listdir(cards_dir) if f.endswith(".json"))


def load_card(card_id, cards_dir=CARDS_DIR):
    path = os.path.join(cards_dir, card_id + ".json")
    with open(path, encoding="utf-8") as fh:
        card = json.load(fh)
    if card.get("id") != card_id:
        raise ValueError("card file %s has id %r" % (path, card.get("id")))
    return card


def unverified_fields(card):
    """Paths of fields whose value mentions 'verify' (unconfirmed content)."""
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "verify" or (isinstance(v, str) and "verify" in v.lower()):
                    found.append(path + [k])
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, str) and "verify" in v.lower():
                    found.append(path + [i])
                walk(v, path + [i])

    walk(card, [])
    return [".".join(str(p) for p in f) for f in found]
