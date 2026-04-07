import streamlit as st

from services.company_alias_service import (
    CompanyAliasService,
    CompanyAliasServiceError,
)
from services.company_news_service import (
    CompanyNewsService,
    CompanyNewsServiceError,
)
from services.company_resolver import (
    CompanyResolver,
    CompanyResolverError,
    get_company_resolver,
)


class UIDashboard:
    SEARCH_BY_NAME = "Search by name"
    SEARCH_BY_REG = "Search by company reg"

    SEARCH_STATE_DEFAULTS = {
        "search_results": [],
        "search_selection": None,
    }

    COMPANY_STATE_DEFAULTS = {
        "loaded_company": None,
        "brand_result": None,
        "brand_error": None,
        "news_result": None,
        "news_error": None,
    }

    STATE_DEFAULTS = {
        **SEARCH_STATE_DEFAULTS,
        **COMPANY_STATE_DEFAULTS,
    }

    def __init__(
        self,
        resolver: CompanyResolver | None = None,
        alias_service: CompanyAliasService | None = None,
        news_service: CompanyNewsService | None = None,
    ):
        self.resolver = resolver or get_company_resolver()
        self.alias_service = alias_service or CompanyAliasService()
        self.news_service = news_service or CompanyNewsService()

    @staticmethod
    def render_header():
        st.write("BY MUHAMMAD TUKUR")
        st.title("Tunic Relic")
        st.caption("This relic is a weapon")

    def _ensure_state(self):
        for key, default in self.STATE_DEFAULTS.items():
            st.session_state.setdefault(key, default)

    def _clear_company_state(self):
        for key, default in self.COMPANY_STATE_DEFAULTS.items():
            st.session_state[key] = default

    @staticmethod
    def _get_registration_number(company: dict) -> str:
        return str(company.get("registration_number")).strip()

    @staticmethod
    def _format_company_option(company: dict) -> str:
        return (
            f"{company.get('company_name')} - "
            f"{company.get('registration_number')} "
            f"({company.get('jurisdiction')})"
        )

    def _fetch_news_for_brand(self, brand: str):
        try:
            with st.spinner("Fetching company news..."):
                st.session_state["news_result"] = self.news_service.fetch_news(brand)
        except CompanyNewsServiceError as exc:
            st.session_state["news_error"] = str(exc)
        except Exception as exc:
            st.session_state["news_error"] = (
                str(exc) or "Something went wrong while fetching company news."
            )

    def _identify_brand_for_company(self, company: dict):
        try:
            with st.spinner("Identifying company brand..."):
                brand_result = self.alias_service.identify_brand(
                    str(company.get("company_name") or "")
                )
            st.session_state["brand_result"] = brand_result
        except CompanyAliasServiceError as exc:
            st.session_state["brand_error"] = str(exc)
            return
        except Exception as exc:
            st.session_state["brand_error"] = (
                str(exc) or "Something went wrong while identifying the company brand."
            )
            return

        brand = str(brand_result.get("brand") or "").strip()
        if brand:
            self._fetch_news_for_brand(brand)

    def _load_company_details(self, registration_number: str):
        self._clear_company_state()
        registration_number = registration_number.strip()

        if not registration_number:
            st.warning("Registration number is required.")
            return

        try:
            with st.spinner("Fetching company details..."):
                company = self.resolver.resolve_by_registration_number(
                    registration_number
                )
        except CompanyResolverError as exc:
            st.error(str(exc))
            return
        except Exception:
            st.error("Something went wrong while fetching company details.")
            return

        st.session_state["loaded_company"] = company
        self._identify_brand_for_company(company)

    def _render_loaded_company_results(self):
        company = st.session_state["loaded_company"]
        if not company:
            return

        st.success("Company found")
        company_details_tab, brand_tab, news_tab = st.tabs(
            ["Company Details", "Brand", "News"]
        )

        with company_details_tab:
            st.json(company)

        with brand_tab:
            st.caption(
                "Brand identification is generated from the loaded company name via OpenRouter."
            )

            brand_error = st.session_state["brand_error"]
            brand_result = st.session_state["brand_result"]

            if brand_error:
                st.error(brand_error)
            elif not brand_result:
                st.info("No brand identification is available for this company.")
            else:
                brand = str(brand_result.get("brand") or "").strip()
                st.write(f"Brand: {brand or 'None'}")

                with st.expander("Raw brand payload"):
                    st.json(brand_result)

        with news_tab:
            st.caption(
                "News is fetched after brand identification for the loaded company."
            )

            news_error = st.session_state["news_error"]
            news_result = st.session_state["news_result"]

            if news_error:
                st.error(news_error)
            elif not news_result:
                st.info("No news is available for this company.")
            else:
                query = str(news_result.get("query") or "").strip()
                if query:
                    st.write(f"Query used: {query}")

                response = news_result.get("response")
                if response is None:
                    st.info("No news response is available for this company.")
                else:
                    st.json(response)

    def render_search_by_name(self):
        with st.form("search_company_form"):
            company_name = st.text_input("Company name", placeholder="Tunic Pay")
            run_search = st.form_submit_button("Find company", type="primary")

        if run_search:
            self._clear_company_state()
            st.session_state["search_selection"] = None

            if not company_name.strip():
                st.warning("Enter a company name.")
                st.session_state["search_results"] = []
                return

            try:
                st.session_state["search_results"] = self.resolver.search_by_name(
                    company_name
                )
            except CompanyResolverError as exc:
                st.error(str(exc))
                st.session_state["search_results"] = []
                return
            except Exception:
                st.error("Something went wrong while searching for companies.")
                st.session_state["search_results"] = []
                return

        results = st.session_state["search_results"]
        if not results:
            return

        options = {self._format_company_option(company): company for company in results}
        labels = list(options.keys())

        if st.session_state["search_selection"] not in options:
            st.session_state["search_selection"] = labels[0]

        choice = st.selectbox(
            "Choose a company",
            labels,
            key="search_selection",
        )

        if st.button("Load company details", type="primary"):
            selected_company = options[choice]
            self._load_company_details(
                self._get_registration_number(selected_company)
            )

    def render_search_by_reg(self):
        with st.form("exact_company_form"):
            registration_number = st.text_input(
                "Registration number",
                placeholder="12345678",
            )
            run_exact = st.form_submit_button("Find company", type="primary")

        if run_exact:
            self._load_company_details(registration_number)

    def run(self):
        self._ensure_state()
        self.render_header()

        mode = st.radio(
            "Choose how to find the company",
            [self.SEARCH_BY_NAME, self.SEARCH_BY_REG],
            horizontal=True,
        )

        if mode == self.SEARCH_BY_NAME:
            self.render_search_by_name()
        else:
            self.render_search_by_reg()

        self._render_loaded_company_results()