from __future__ import annotations

"""Catálogo mínimo de códigos TIM Backoffice/ANATEL preservados pelo framework.

O framework não implementa regra de negócio de backoffice aqui; ele apenas
padroniza os nomes para que agentes nativos emitam os mesmos códigos que o
backoffice original mostrava no Langfuse.
"""

# AGA - Itens de Controle do fluxo agentico/backoffice
AGA_001 = "AGA.001"
AGA_002 = "AGA.002"
AGA_003 = "AGA.003"
AGA_004 = "AGA.004"
AGA_005 = "AGA.005"
AGA_006 = "AGA.006"
AGA_007 = "AGA.007"
AGA_008 = "AGA.008"
AGA_009 = "AGA.009"
AGA_010 = "AGA.010"
AGA_011 = "AGA.011"
AGA_012 = "AGA.012"
AGA_014 = "AGA.014"
AGA_015 = "AGA.015"
AGA_018 = "AGA.018"
AGA_019 = "AGA.019"
AGA_020 = "AGA.020"
AGA_021 = "AGA.021"
AGA_022 = "AGA.022"
AGA_023 = "AGA.023"
AGA_024 = "AGA.024"
AGA_025 = "AGA.025"
AGA_027 = "AGA.027"
AGA_028 = "AGA.028"
AGA_029 = "AGA.029"
AGA_030 = "AGA.030"
AGA_031 = "AGA.031"
AGA_032 = "AGA.032"
AGA_033 = "AGA.033"
AGA_034 = "AGA.034"
AGA_035 = "AGA.035"
AGA_036 = "AGA.036"
AGA_037 = "AGA.037"
AGA_038 = "AGA.038"
AGA_039 = "AGA.039"
AGA_040 = "AGA.040"
AGA_041 = "AGA.041"
AGA_042 = "AGA.042"
AGA_043 = "AGA.043"

# NOC - eventos operacionais observáveis
NOC_001 = "NOC.001"
NOC_002 = "NOC.002"
NOC_003 = "NOC.003"
NOC_004 = "NOC.004"
NOC_005 = "NOC.005"
NOC_006 = "NOC.006"
NOC_007 = "NOC.007"
NOC_008 = "NOC.008"
NOC_009 = "NOC.009"

__all__ = [name for name in globals() if name.startswith(("AGA_", "NOC_"))]
