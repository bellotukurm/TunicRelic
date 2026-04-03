import streamlit as st

from services.company_alias_service import (
    CompanyAliasService,
    CompanyAliasServiceError,
)
from services.company_resolver import (
    CompanyResolver,
    CompanyResolverError,
    get_company_resolver,
)


class UIDashboard:
    def __init__(
        self,
        resolver: CompanyResolver | None = None,
        alias_service: CompanyAliasService | None = None,
    ):
        self.search_by_name = "Search by name"
        self.search_by_reg = "Search by company reg"
        self.resolver = resolver if resolver is not None else get_company_resolver()
        self.alias_service = alias_service
        self.search_results_key = "search_results"
        self.search_selection_key = "search_selection"
        self.loaded_company_key = "loaded_company"
        self.alias_result_key = "company_alias_result"
        self.alias_error_key = "company_alias_error"
        self.alias_company_key = "company_alias_company_key"

    def render_header(self):
        st.write("BY MUHAMMAD TUKUR")
        st.title("Tunic Relic")
        st.caption("This relic is a weapon")

    def _ensure_state(self):
        st.session_state.setdefault(self.search_results_key, [])
        st.session_state.setdefault(self.loaded_company_key, None)
        st.session_state.setdefault(self.alias_result_key, None)
        st.session_state.setdefault(self.alias_error_key, None)
        st.session_state.setdefault(self.alias_company_key, None)

    def _clear_loaded_company_state(self):
        st.session_state[self.loaded_company_key] = None
        st.session_state[self.alias_result_key] = None
        st.session_state[self.alias_error_key] = None
        st.session_state[self.alias_company_key] = None

    def _format_company_option(self, company: dict) -> str:
        return (
            f"{company.get('company_name')} - "
            f"{company.get('registration_number')} "
            f"({company.get('jurisdiction')})"
        )

    def _get_registration_number(self, company: dict) -> str:
        return str(
            company.get("registration_number") or company.get("company_number") or ""
        ).strip()

    def _get_alias_service(self) -> CompanyAliasService:
        if self.alias_service is None:
            self.alias_service = CompanyAliasService()
        return self.alias_service

    def _extract_previous_names(self, company: dict) -> list[str]:
        previous_company_names = company.get("previous_company_names") or []
        if not isinstance(previous_company_names, list):
            return []

        previous_names: list[str] = []
        for item in previous_company_names:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item or "").strip()

            if name:
                previous_names.append(name)

        return previous_names

    def _build_alias_request(self, company: dict) -> dict:
        registered_office_address = company.get("registered_office_address") or {}
        country = None
        if isinstance(registered_office_address, dict):
            country = str(registered_office_address.get("country") or "").strip() or None

        if not country:
            country = str(company.get("country_of_origin") or "").strip() or None

        return {
            "legal_name": str(company.get("company_name") or "").strip(),
            "registration_number": self._get_registration_number(company) or None,
            "domain": None,
            "previous_names": self._extract_previous_names(company),
            "country": country,
        }

    def _format_alias_confidence(self, confidence: object) -> str:
        if isinstance(confidence, (int, float)):
            return f"{float(confidence):.2f}"

        return "N/A"

    def _generate_aliases_for_company(self, company: dict):
        company_key = self._get_registration_number(company) or None
        st.session_state[self.alias_result_key] = None
        st.session_state[self.alias_error_key] = None
        st.session_state[self.alias_company_key] = company_key

        try:
            alias_request = self._build_alias_request(company)
            with st.spinner("Generating company aliases..."):
                alias_result = self._get_alias_service().generate_news_aliases(
                    alias_request
                )
        except CompanyAliasServiceError as exc:
            st.session_state[self.alias_error_key] = str(exc)
        except Exception as exc:
            st.session_state[self.alias_error_key] = (
                str(exc)
                or "Something went wrong while generating company aliases."
            )
        else:
            st.session_state[self.alias_result_key] = alias_result

    def _load_company_details(self, registration_number: str):
        registration_number = registration_number.strip()
        self._clear_loaded_company_state()

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

        st.session_state[self.loaded_company_key] = company
        self._generate_aliases_for_company(company)

    def _render_company_details_tab(self, company: dict):
        st.json(company)

    def _render_aliases_tab(self, company: dict):
        st.caption("Aliases are generated from the loaded company profile via OpenRouter.")

        company_key = self._get_registration_number(company) or None
        alias_company_key = st.session_state[self.alias_company_key]
        if alias_company_key != company_key:
            st.info("Aliases are not available for this company yet.")
            return

        alias_error = st.session_state[self.alias_error_key]
        if alias_error:
            st.error(alias_error)
            return

        alias_result = st.session_state[self.alias_result_key]
        if not alias_result:
            st.info("No aliases are available for this company.")
            return

        news_aliases = alias_result.get("news_aliases", [])
        if news_aliases:
            alias_rows = [
                {
                    "Alias": alias.get("alias"),
                    "Confidence": self._format_alias_confidence(
                        alias.get("confidence")
                    ),
                    "Reason": alias.get("reason"),
                }
                for alias in news_aliases
            ]
            st.dataframe(alias_rows, width='stretch')
        else:
            st.info("No aliases were generated for this company.")

        with st.expander("Raw alias payload"):
            st.json(alias_result)

    def _render_loaded_company_results(self):
        company = st.session_state[self.loaded_company_key]
        if not company:
            return

        st.success("Company found")
        company_details_tab, aliases_tab = st.tabs(["Company Details", "Aliases"])

        with company_details_tab:
            self._render_company_details_tab(company)

        with aliases_tab:
            self._render_aliases_tab(company)

    def render_search_by_name(self):
        show_no_results_message = False

        with st.form("search_company_form"):
            company_name = st.text_input(
                "Company name",
                placeholder="Tunic Pay",
            )
            run_search = st.form_submit_button("Find company", type="primary")

        if run_search:
            self._clear_loaded_company_state()
            st.session_state.pop(self.search_selection_key, None)

            if not company_name.strip():
                st.warning("Enter a company name.")
                st.session_state[self.search_results_key] = []
                return

            try:
                results = self.resolver.search_by_name(company_name)
            except CompanyResolverError as exc:
                st.error(str(exc))
                st.session_state[self.search_results_key] = []
                return
            except Exception:
                st.error("Something went wrong while searching for companies.")
                st.session_state[self.search_results_key] = []
                return

            st.session_state[self.search_results_key] = results
            show_no_results_message = not results

        results = st.session_state[self.search_results_key]
        if not results:
            if show_no_results_message:
                st.info("No companies found.")
            return

        options = {self._format_company_option(company): company for company in results}
        option_labels = list(options.keys())

        current_selection = st.session_state.get(self.search_selection_key)
        if current_selection not in options:
            st.session_state[self.search_selection_key] = option_labels[0]

        choice = st.selectbox(
            "Choose a company",
            option_labels,
            key=self.search_selection_key,
        )

        selected_company = options[choice]
        if st.button("Load company details", type="primary"):
            registration_number = selected_company.get("registration_number", "")
            self._load_company_details(registration_number)

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
            [self.search_by_name, self.search_by_reg],
            horizontal=True,
        )

        if mode == self.search_by_name:
            self.render_search_by_name()
        else:
            self.render_search_by_reg()

        self._render_loaded_company_results()
