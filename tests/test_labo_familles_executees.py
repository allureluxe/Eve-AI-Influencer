from gold_bot.lab import REGLAGES_PAR_FAMILLE, reglages_sans_effet
from ops.labo_recherche import FAMILLES_EXECUTABLES

def test_familles_risque_volatilite_executees():
    assert {'risque','volatilite'} <= FAMILLES_EXECUTABLES
    assert 'min_rr' in REGLAGES_PAR_FAMILLE['risque']
    assert 'min_atr_percentile' in REGLAGES_PAR_FAMILLE['volatilite']
    assert not reglages_sans_effet({'min_rr': 1.8}, 'risque')
    assert not reglages_sans_effet({'min_atr_percentile': 0.3}, 'volatilite')
