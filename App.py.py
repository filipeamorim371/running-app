import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go

from datetime import date, timedelta


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Running",
    page_icon="🏃",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 780px;
        padding-top: 1.2rem;
        padding-bottom: 4rem;
    }

    h1 {
        letter-spacing: -0.04em;
    }

    h2, h3 {
        letter-spacing: -0.02em;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.22);
        padding: 14px;
        border-radius: 16px;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 18px;
    }

    div[data-testid="stProgress"] > div > div {
        border-radius: 999px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# BANCO DE DADOS
# =========================================================

DB = "corrida.db"


def conectar():
    return sqlite3.connect(DB, check_same_thread=False)


def coluna_existe(tabela, coluna):
    with conectar() as conexao:
        colunas = conexao.execute(
            f"PRAGMA table_info({tabela})"
        ).fetchall()

    nomes = [linha[1] for linha in colunas]
    return coluna in nomes


with conectar() as conexao:
    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS treinos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            tipo TEXT,
            distancia REAL,
            pace TEXT,
            esforco INTEGER,
            observacao TEXT
        )
        """
    )

    conexao.execute(
        """
        CREATE TABLE IF NOT EXISTS planejamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            tipo TEXT,
            distancia REAL,
            pace_alvo TEXT,
            descricao TEXT
        )
        """
    )

    conexao.commit()


# Migração simples para manter compatibilidade com seu banco atual
if not coluna_existe("treinos", "planejamento_id"):
    with conectar() as conexao:
        conexao.execute(
            "ALTER TABLE treinos ADD COLUMN planejamento_id INTEGER"
        )
        conexao.commit()


# =========================================================
# FUNÇÕES DE DADOS
# =========================================================

def salvar_treino(
    data_treino,
    tipo,
    distancia,
    pace,
    esforco,
    observacao,
    planejamento_id=None,
):
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO treinos
            (
                data,
                tipo,
                distancia,
                pace,
                esforco,
                observacao,
                planejamento_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(data_treino),
                tipo,
                float(distancia),
                pace.strip(),
                int(esforco),
                observacao.strip(),
                planejamento_id,
            ),
        )
        conexao.commit()


def salvar_planejamento(
    data_treino,
    tipo,
    distancia,
    pace_alvo,
    descricao,
):
    with conectar() as conexao:
        conexao.execute(
            """
            INSERT INTO planejamento
            (
                data,
                tipo,
                distancia,
                pace_alvo,
                descricao
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(data_treino),
                tipo,
                float(distancia),
                pace_alvo.strip(),
                descricao.strip(),
            ),
        )
        conexao.commit()


def excluir_planejamento(id_treino):
    with conectar() as conexao:
        conexao.execute(
            "DELETE FROM planejamento WHERE id = ?",
            (int(id_treino),),
        )
        conexao.commit()


def excluir_treino(id_treino):
    with conectar() as conexao:
        conexao.execute(
            "DELETE FROM treinos WHERE id = ?",
            (int(id_treino),),
        )
        conexao.commit()


def carregar_planejamento():
    with conectar() as conexao:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM planejamento
            ORDER BY data, id
            """,
            conexao,
        )

    if not df.empty:
        df["data_dt"] = pd.to_datetime(
            df["data"],
            errors="coerce",
        ).dt.date

    return df


def carregar_historico():
    with conectar() as conexao:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM treinos
            ORDER BY data DESC, id DESC
            """,
            conexao,
        )

    if not df.empty:
        df["data_dt"] = pd.to_datetime(
            df["data"],
            errors="coerce",
        ).dt.date

    return df


# =========================================================
# FUNÇÕES DE PACE
# =========================================================

def pace_para_segundos(pace):
    if pace is None:
        return None

    texto = str(pace).strip()

    if not texto:
        return None

    texto = (
        texto.replace("'", ":")
        .replace('"', "")
        .replace("/km", "")
        .strip()
    )

    try:
        partes = texto.split(":")

        if len(partes) != 2:
            return None

        minutos = int(partes[0])
        segundos = int(partes[1])

        if minutos < 0 or segundos < 0 or segundos >= 60:
            return None

        return minutos * 60 + segundos

    except (ValueError, TypeError):
        return None


def segundos_para_pace(segundos):
    if segundos is None or pd.isna(segundos):
        return "-"

    valor = int(round(float(segundos)))
    minutos = valor // 60
    resto = valor % 60

    return f"{minutos}:{resto:02d}"


def tempo_5k_por_pace(pace_segundos):
    if pace_segundos is None:
        return None

    return pace_segundos * 5


def segundos_para_tempo(segundos):
    if segundos is None or pd.isna(segundos):
        return "-"

    valor = int(round(float(segundos)))
    minutos = valor // 60
    resto = valor % 60

    return f"{minutos}:{resto:02d}"


# =========================================================
# FUNÇÕES DE RELAÇÃO PLANEJADO x REALIZADO
# =========================================================

def realizado_do_planejado(treino_planejado, historico_df):
    if historico_df.empty:
        return None

    # Primeiro tenta vínculo direto
    direto = historico_df[
        historico_df["planejamento_id"]
        == treino_planejado["id"]
    ]

    if not direto.empty:
        return direto.iloc[0]

    # Compatibilidade com treinos antigos:
    # tenta casar por data + tipo
    fallback = historico_df[
        (historico_df["data"] == treino_planejado["data"])
        & (historico_df["tipo"] == treino_planejado["tipo"])
    ]

    if not fallback.empty:
        return fallback.iloc[0]

    return None


# =========================================================
# DATAS E CONSTANTES
# =========================================================

hoje = date.today()

inicio_semana = hoje - timedelta(
    days=hoje.weekday()
)

fim_semana = inicio_semana + timedelta(days=6)

dias_completos = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}

dias_curtos = {
    0: "SEG",
    1: "TER",
    2: "QUA",
    3: "QUI",
    4: "SEX",
    5: "SÁB",
    6: "DOM",
}

tipos_treino = [
    "Rodagem leve",
    "Progressivo",
    "Intervalado",
    "Longão",
    "Tempo Run",
    "Teste 5 km",
    "Outro",
]

META_5K_SEG = 25 * 60
RECORDE_5K_SEG = 24 * 60 + 20
PACE_META_5K = META_5K_SEG / 5
PACE_RECORDE_5K = RECORDE_5K_SEG / 5


# =========================================================
# CARREGAMENTO
# =========================================================

planejamento = carregar_planejamento()
historico = carregar_historico()

if not planejamento.empty:
    semana_planejada = planejamento[
        (planejamento["data_dt"] >= inicio_semana)
        & (planejamento["data_dt"] <= fim_semana)
    ].copy()
else:
    semana_planejada = pd.DataFrame()

if not historico.empty:
    semana_realizada = historico[
        (historico["data_dt"] >= inicio_semana)
        & (historico["data_dt"] <= fim_semana)
    ].copy()
else:
    semana_realizada = pd.DataFrame()


# =========================================================
# CABEÇALHO
# =========================================================

st.title("🏃 Running")
st.caption("Treino, evolução e consistência.")


# =========================================================
# ABAS
# =========================================================

(
    hoje_tab,
    semana_tab,
    planejar_tab,
    historico_tab,
    evolucao_tab,
) = st.tabs(
    [
        "Hoje",
        "Semana",
        "Planejar",
        "Histórico",
        "Evolução",
    ]
)


# =========================================================
# HOJE
# =========================================================

with hoje_tab:
    st.write("")

    with st.container(border=True):
        st.caption(
            dias_completos[hoje.weekday()].upper()
        )
        st.markdown(
            f"# {hoje.strftime('%d/%m')}"
        )

        if not semana_planejada.empty:
            treino_hoje_df = semana_planejada[
                semana_planejada["data_dt"] == hoje
            ]
        else:
            treino_hoje_df = pd.DataFrame()

        if treino_hoje_df.empty:
            st.write("Dia sem treino planejado.")
        else:
            pendentes_hoje = 0

            for _, treino in treino_hoje_df.iterrows():
                realizado = realizado_do_planejado(
                    treino,
                    historico,
                )

                if realizado is None:
                    pendentes_hoje += 1

            if pendentes_hoje == 0:
                st.success(
                    "Treino de hoje concluído."
                )
            else:
                st.write(
                    "Você tem treino planejado para hoje."
                )

    st.write("")
    st.subheader("Treino de hoje")

    if treino_hoje_df.empty:
        st.info(
            "Hoje não há treino planejado."
        )
    else:
        for _, treino in treino_hoje_df.iterrows():
            realizado = realizado_do_planejado(
                treino,
                historico,
            )

            with st.container(border=True):
                topo1, topo2 = st.columns(
                    [3, 1]
                )

                topo1.markdown(
                    f"### {treino['tipo']}"
                )

                if realizado is None:
                    topo2.write("○ Pendente")
                else:
                    topo2.write("✅ Feito")

                c1, c2 = st.columns(2)

                c1.metric(
                    "Planejado",
                    (
                        f"{treino['distancia']:.1f} km"
                        if treino["distancia"] > 0
                        else "-"
                    ),
                )

                c2.metric(
                    "Pace alvo",
                    (
                        treino["pace_alvo"]
                        if treino["pace_alvo"]
                        else "-"
                    ),
                )

                if treino["descricao"]:
                    st.caption(
                        treino["descricao"]
                    )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = st.columns(3)

                    r1.metric(
                        "Realizado",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace real",
                        (
                            realizado["pace"]
                            if realizado["pace"]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "Esforço",
                        f"{int(realizado['esforco'])}/10",
                    )

                    if realizado["observacao"]:
                        st.caption(
                            realizado["observacao"]
                        )

                else:
                    with st.expander(
                        "Concluir este treino",
                        expanded=False,
                    ):
                        with st.form(
                            f"concluir_{int(treino['id'])}"
                        ):
                            distancia_real = st.number_input(
                                "Distância realizada (km)",
                                min_value=0.0,
                                value=float(
                                    treino["distancia"]
                                ),
                                step=0.1,
                                key=f"dist_real_{int(treino['id'])}",
                            )

                            pace_real = st.text_input(
                                "Pace médio",
                                placeholder="Ex.: 6:15",
                                key=f"pace_real_{int(treino['id'])}",
                            )

                            esforco_real = st.slider(
                                "Esforço percebido",
                                min_value=1,
                                max_value=10,
                                value=5,
                                key=f"esf_real_{int(treino['id'])}",
                            )

                            observacao_real = st.text_area(
                                "Observações",
                                placeholder="Como foi o treino?",
                                key=f"obs_real_{int(treino['id'])}",
                            )

                            concluir = st.form_submit_button(
                                "Salvar como concluído",
                                use_container_width=True,
                            )

                            if concluir:
                                if distancia_real <= 0:
                                    st.warning(
                                        "Informe a distância realizada."
                                    )
                                elif (
                                    pace_real
                                    and pace_para_segundos(
                                        pace_real
                                    )
                                    is None
                                ):
                                    st.warning(
                                        "Use o formato min:seg. Ex.: 6:15"
                                    )
                                else:
                                    salvar_treino(
                                        treino["data"],
                                        treino["tipo"],
                                        distancia_real,
                                        pace_real,
                                        esforco_real,
                                        observacao_real,
                                        int(treino["id"]),
                                    )

                                    st.rerun()

    st.write("")

    with st.expander(
        "Registrar treino extra"
    ):
        with st.form(
            "registrar_treino_extra"
        ):
            data_extra = st.date_input(
                "Data",
                value=hoje,
            )

            tipo_extra = st.selectbox(
                "Tipo de treino",
                tipos_treino,
                key="tipo_extra",
            )

            distancia_extra = st.number_input(
                "Distância realizada (km)",
                min_value=0.0,
                step=0.1,
                key="dist_extra",
            )

            pace_extra = st.text_input(
                "Pace médio",
                placeholder="Ex.: 6:15",
                key="pace_extra",
            )

            esforco_extra = st.slider(
                "Esforço percebido",
                min_value=1,
                max_value=10,
                value=5,
                key="esf_extra",
            )

            observacao_extra = st.text_area(
                "Observações",
                key="obs_extra",
            )

            salvar_extra = st.form_submit_button(
                "Salvar treino extra",
                use_container_width=True,
            )

            if salvar_extra:
                if distancia_extra <= 0:
                    st.warning(
                        "Informe a distância realizada."
                    )
                elif (
                    pace_extra
                    and pace_para_segundos(
                        pace_extra
                    )
                    is None
                ):
                    st.warning(
                        "Use o formato min:seg. Ex.: 6:15"
                    )
                else:
                    salvar_treino(
                        data_extra,
                        tipo_extra,
                        distancia_extra,
                        pace_extra,
                        esforco_extra,
                        observacao_extra,
                        None,
                    )

                    st.rerun()


# =========================================================
# SEMANA
# =========================================================

with semana_tab:
    st.subheader("Sua semana")
    st.caption(
        f"{inicio_semana.strftime('%d/%m')} "
        f"até {fim_semana.strftime('%d/%m')}"
    )

    total_planejados = len(
        semana_planejada
    )

    concluidos = 0

    if not semana_planejada.empty:
        for _, treino in semana_planejada.iterrows():
            if realizado_do_planejado(
                treino,
                historico,
            ) is not None:
                concluidos += 1

    km_planejados = (
        semana_planejada["distancia"].sum()
        if not semana_planejada.empty
        else 0
    )

    km_realizados = (
        semana_realizada["distancia"].sum()
        if not semana_realizada.empty
        else 0
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Concluídos",
        f"{concluidos}/{total_planejados}",
    )

    c2.metric(
        "Planejado",
        f"{km_planejados:.1f} km",
    )

    c3.metric(
        "Realizado",
        f"{km_realizados:.1f} km",
    )

    if total_planejados > 0:
        progresso = concluidos / total_planejados
        st.progress(progresso)
        st.caption(
            f"{progresso * 100:.0f}% dos treinos planejados concluídos"
        )

    st.write("")

    if semana_planejada.empty:
        st.info(
            "Nenhum treino planejado nesta semana."
        )
    else:
        for _, treino in semana_planejada.iterrows():
            data_treino = treino["data_dt"]

            realizado = realizado_do_planejado(
                treino,
                historico,
            )

            with st.container(border=True):
                topo1, topo2 = st.columns(
                    [3, 1]
                )

                topo1.caption(
                    f"{dias_curtos[data_treino.weekday()]} "
                    f"· {data_treino.strftime('%d/%m')}"
                )

                topo1.markdown(
                    f"### {treino['tipo']}"
                )

                if realizado is None:
                    topo2.write("○ Pendente")
                else:
                    topo2.write("✅ Feito")

                p1, p2 = st.columns(2)

                p1.metric(
                    "Planejado",
                    (
                        f"{treino['distancia']:.1f} km"
                        if treino["distancia"] > 0
                        else "-"
                    ),
                )

                p2.metric(
                    "Pace alvo",
                    (
                        treino["pace_alvo"]
                        if treino["pace_alvo"]
                        else "-"
                    ),
                )

                if treino["descricao"]:
                    st.caption(
                        treino["descricao"]
                    )

                if realizado is not None:
                    st.divider()

                    r1, r2, r3 = st.columns(3)

                    r1.metric(
                        "Real",
                        f"{realizado['distancia']:.1f} km",
                    )

                    r2.metric(
                        "Pace",
                        (
                            realizado["pace"]
                            if realizado["pace"]
                            else "-"
                        ),
                    )

                    r3.metric(
                        "RPE",
                        f"{int(realizado['esforco'])}/10",
                    )

                else:
                    with st.expander(
                        "Registrar resultado"
                    ):
                        with st.form(
                            f"semana_concluir_{int(treino['id'])}"
                        ):
                            dist = st.number_input(
                                "Distância realizada",
                                min_value=0.0,
                                value=float(
                                    treino["distancia"]
                                ),
                                step=0.1,
                                key=f"sem_dist_{int(treino['id'])}",
                            )

                            pace = st.text_input(
                                "Pace médio",
                                placeholder="Ex.: 6:15",
                                key=f"sem_pace_{int(treino['id'])}",
                            )

                            rpe = st.slider(
                                "Esforço percebido",
                                1,
                                10,
                                5,
                                key=f"sem_rpe_{int(treino['id'])}",
                            )

                            obs = st.text_area(
                                "Observações",
                                key=f"sem_obs_{int(treino['id'])}",
                            )

                            salvar_resultado = (
                                st.form_submit_button(
                                    "Concluir treino",
                                    use_container_width=True,
                                )
                            )

                            if salvar_resultado:
                                if dist <= 0:
                                    st.warning(
                                        "Informe a distância."
                                    )
                                elif (
                                    pace
                                    and pace_para_segundos(
                                        pace
                                    )
                                    is None
                                ):
                                    st.warning(
                                        "Use o formato min:seg. Ex.: 6:15"
                                    )
                                else:
                                    salvar_treino(
                                        treino["data"],
                                        treino["tipo"],
                                        dist,
                                        pace,
                                        rpe,
                                        obs,
                                        int(treino["id"]),
                                    )

                                    st.rerun()

    if not semana_realizada.empty:
        extras = semana_realizada[
            semana_realizada["planejamento_id"].isna()
        ]

        if not extras.empty:
            st.divider()
            st.subheader(
                "Treinos extras"
            )

            for _, treino in extras.iterrows():
                with st.container(border=True):
                    st.caption(
                        treino["data_dt"].strftime(
                            "%d/%m"
                        )
                    )
                    st.markdown(
                        f"### {treino['tipo']}"
                    )

                    x1, x2, x3 = st.columns(3)

                    x1.metric(
                        "Distância",
                        f"{treino['distancia']:.1f} km",
                    )

                    x2.metric(
                        "Pace",
                        (
                            treino["pace"]
                            if treino["pace"]
                            else "-"
                        ),
                    )

                    x3.metric(
                        "RPE",
                        f"{int(treino['esforco'])}/10",
                    )


# =========================================================
# PLANEJAR
# =========================================================

with planejar_tab:
    st.subheader("Novo treino")

    with st.form(
        "planejamento_form",
        clear_on_submit=True,
    ):
        data_planejada = st.date_input(
            "Data do treino",
            value=hoje,
        )

        tipo_planejado = st.selectbox(
            "Tipo de treino",
            tipos_treino,
            key="tipo_planejado",
        )

        distancia_planejada = st.number_input(
            "Distância prevista (km)",
            min_value=0.0,
            step=0.1,
        )

        pace_planejado = st.text_input(
            "Pace alvo",
            placeholder="Ex.: 6:20, 4:55 ou Livre",
        )

        descricao_planejada = st.text_area(
            "Orientações",
            placeholder=(
                "Ex.: 1 km aquecimento + "
                "6 x 400 m + 1 km desaquecimento."
            ),
        )

        adicionar = st.form_submit_button(
            "Adicionar treino",
            use_container_width=True,
        )

        if adicionar:
            salvar_planejamento(
                data_planejada,
                tipo_planejado,
                distancia_planejada,
                pace_planejado,
                descricao_planejada,
            )

            st.rerun()

    st.divider()
    st.subheader("Próximos treinos")

    planejamento_atual = carregar_planejamento()

    if planejamento_atual.empty:
        st.info(
            "Nenhum treino planejado."
        )
    else:
        futuros = planejamento_atual[
            planejamento_atual["data_dt"] >= hoje
        ]

        if futuros.empty:
            st.info(
                "Nenhum treino futuro."
            )
        else:
            for _, treino in futuros.iterrows():
                realizado = realizado_do_planejado(
                    treino,
                    historico,
                )

                with st.container(border=True):
                    c1, c2 = st.columns(
                        [3, 1]
                    )

                    c1.caption(
                        treino["data_dt"].strftime(
                            "%d/%m/%Y"
                        )
                    )

                    c1.markdown(
                        f"### {treino['tipo']}"
                    )

                    if realizado is None:
                        c2.write("○")
                    else:
                        c2.write("✅")

                    st.write(
                        (
                            f"📏 {treino['distancia']:.1f} km"
                            if treino["distancia"] > 0
                            else "📏 Distância livre"
                        )
                    )

                    if treino["pace_alvo"]:
                        st.write(
                            f"🎯 {treino['pace_alvo']}"
                        )

                    if treino["descricao"]:
                        st.caption(
                            treino["descricao"]
                        )

                    if realizado is None:
                        if st.button(
                            "Excluir",
                            key=f"excluir_plan_{int(treino['id'])}",
                            use_container_width=True,
                        ):
                            excluir_planejamento(
                                treino["id"]
                            )
                            st.rerun()


# =========================================================
# HISTÓRICO
# =========================================================

with historico_tab:
    st.subheader("Histórico")

    historico_atual = carregar_historico()

    if historico_atual.empty:
        st.info(
            "Nenhum treino registrado."
        )
    else:
        for _, treino in historico_atual.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns(
                    [4, 1]
                )

                c1.caption(
                    treino["data_dt"].strftime(
                        "%d/%m/%Y"
                    )
                )

                c1.markdown(
                    f"### {treino['tipo']}"
                )

                if c2.button(
                    "🗑️",
                    key=f"excluir_real_{int(treino['id'])}",
                    help="Excluir treino",
                ):
                    excluir_treino(
                        treino["id"]
                    )
                    st.rerun()

                m1, m2, m3 = st.columns(3)

                m1.metric(
                    "Distância",
                    f"{treino['distancia']:.1f} km",
                )

                m2.metric(
                    "Pace",
                    (
                        treino["pace"]
                        if treino["pace"]
                        else "-"
                    ),
                )

                m3.metric(
                    "RPE",
                    f"{int(treino['esforco'])}/10",
                )

                if treino["observacao"]:
                    st.caption(
                        treino["observacao"]
                    )


# =========================================================
# EVOLUÇÃO
# =========================================================

with evolucao_tab:
    st.subheader("Meta 5 km")

    meta1, meta2, meta3 = st.columns(3)

    meta1.metric(
        "Objetivo",
        "< 25:00",
    )

    meta2.metric(
        "Pace-alvo",
        "4:59/km",
    )

    meta3.metric(
        "Recorde",
        "24:20",
    )

    st.caption(
        "Seu recorde equivale a aproximadamente "
        f"{segundos_para_pace(PACE_RECORDE_5K)}/km."
    )

    st.divider()

    historico_atual = carregar_historico()

    if historico_atual.empty:
        st.info(
            "Registre treinos para visualizar sua evolução."
        )
    else:
        total_km = historico_atual["distancia"].sum()
        quantidade = len(historico_atual)
        media_esforco = historico_atual["esforco"].mean()

        e1, e2, e3 = st.columns(3)

        e1.metric(
            "Treinos",
            quantidade,
        )

        e2.metric(
            "Km acumulados",
            f"{total_km:.1f}",
        )

        e3.metric(
            "RPE médio",
            f"{media_esforco:.1f}",
        )

        # -----------------------------
        # PACE
        # -----------------------------

        grafico_pace = historico_atual.copy()

        grafico_pace["data_plot"] = pd.to_datetime(
            grafico_pace["data"]
        )

        grafico_pace["pace_segundos"] = (
            grafico_pace["pace"]
            .apply(pace_para_segundos)
        )

        grafico_pace = grafico_pace.dropna(
            subset=["pace_segundos"]
        ).sort_values("data_plot")

        if not grafico_pace.empty:
            st.write("")
            st.subheader("Pace por treino")

            fig_pace = go.Figure()

            fig_pace.add_trace(
                go.Scatter(
                    x=grafico_pace["data_plot"],
                    y=grafico_pace["pace_segundos"],
                    mode="lines+markers",
                    name="Pace",
                    customdata=grafico_pace[
                        ["tipo", "distancia", "pace"]
                    ],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b>"
                        "<br>%{customdata[1]:.1f} km"
                        "<br>%{customdata[2]}/km"
                        "<extra></extra>"
                    ),
                )
            )

            min_pace = int(
                grafico_pace["pace_segundos"].min()
            )

            max_pace = int(
                grafico_pace["pace_segundos"].max()
            )

            inicio = max(
                0,
                ((min_pace - 30) // 15) * 15,
            )

            fim = (
                ((max_pace + 30 + 14) // 15)
                * 15
            )

            ticks = list(
                range(
                    inicio,
                    fim + 15,
                    15,
                )
            )

            fig_pace.update_layout(
                height=350,
                margin=dict(
                    l=10,
                    r=10,
                    t=20,
                    b=10,
                ),
                xaxis_title=None,
                yaxis_title="Pace",
                hovermode="x unified",
            )

            fig_pace.update_yaxes(
                autorange="reversed",
                tickmode="array",
                tickvals=ticks,
                ticktext=[
                    segundos_para_pace(x)
                    for x in ticks
                ],
            )

            st.plotly_chart(
                fig_pace,
                use_container_width=True,
            )

            st.caption(
                "Quanto mais alto o ponto no gráfico, mais rápido foi o pace."
            )

        # -----------------------------
        # VOLUME SEMANAL
        # -----------------------------

        st.divider()
        st.subheader("Volume semanal")

        volume = historico_atual.copy()

        volume["data_plot"] = pd.to_datetime(
            volume["data"]
        )

        volume["semana"] = (
            volume["data_plot"]
            - pd.to_timedelta(
                volume["data_plot"].dt.weekday,
                unit="D",
            )
        )

        volume_semanal = (
            volume.groupby("semana", as_index=False)[
                "distancia"
            ]
            .sum()
            .sort_values("semana")
        )

        st.bar_chart(
            volume_semanal.set_index(
                "semana"
            )["distancia"],
            use_container_width=True,
        )

        # -----------------------------
        # TESTES 5 KM
        # -----------------------------

        testes = grafico_pace[
            grafico_pace["tipo"] == "Teste 5 km"
        ].copy()

        if not testes.empty:
            testes["tempo_5k"] = (
                testes["pace_segundos"] * 5
            )

            melhor_idx = testes[
                "tempo_5k"
            ].idxmin()

            melhor = testes.loc[
                melhor_idx
            ]

            melhor_tempo = melhor[
                "tempo_5k"
            ]

            st.divider()
            st.subheader("Teste de 5 km")

            t1, t2 = st.columns(2)

            t1.metric(
                "Melhor teste",
                segundos_para_tempo(
                    melhor_tempo
                ),
            )

            diferenca = (
                melhor_tempo
                - META_5K_SEG
            )

            if diferenca > 0:
                t2.metric(
                    "Faltam",
                    f"{int(round(diferenca))} s",
                )
            else:
                t2.metric(
                    "Meta",
                    "Sub-25 ✅",
                )
