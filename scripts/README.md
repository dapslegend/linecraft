# Scripts

Offline analysis copied from the weekend research folder.

Included:

- `odds_signal.py` — implied probability, proportional de-vig, Shin de-vig, entropy, KL
- `market_picker.py` — ranks a saved event payload by hold and market family
- `test_market_picker.py` — regression tests for that ranker

Not included: network clients, share booking, stake placement, mail senders, or credentials.

```bash
cd scripts
python3 odds_signal.py
python3 test_market_picker.py
```
