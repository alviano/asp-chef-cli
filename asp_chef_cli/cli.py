import dataclasses
import fileinput
from enum import Enum

import typer
from dumbo_utils.console import console
from dumbo_utils.url import compress_object_for_url
from dumbo_utils.validation import validate
from playwright.sync_api import sync_playwright, Playwright, Error


class Browser(str, Enum):
    CHROMIUM = "chromium"
    # CHROME = "chrome"
    # CHROME_BETA = "chrome-beta"
    # MS_EDGE = "msedge"
    # MS_EDGE_BETA = "msedge-beta"
    # MS_EDGE_DEV = "msedge-dev"
    FIREFOX = "firefox"
    WEBKIT = "webkit"

    def get(self, playwright: Playwright):
        if self == Browser.CHROMIUM:
            return playwright.chromium
        if self == Browser.FIREFOX:
            return playwright.firefox
        if self == Browser.WEBKIT:
            return playwright.webkit
        raise ValueError


@dataclasses.dataclass(frozen=True)
class AppOptions:
    recipe_url: str = dataclasses.field(default="")
    headless: bool = dataclasses.field(default=False)
    browser: Browser = dataclasses.field(default=Browser.FIREFOX)
    debug: bool = dataclasses.field(default=False)


app_options = AppOptions()
app = typer.Typer()


def is_debug_on():
    return app_options.debug


def run_app():
    try:
        app()
    except Exception as e:
        if is_debug_on():
            raise e
        else:
            console.print(f"[red bold]Error:[/red bold] {e}")


def version_callback(value: bool):
    if value:
        import importlib.metadata
        __version__ = importlib.metadata.version("asp-chef-cli")
        console.print("asp-chef-cli", __version__)
        raise typer.Exit()


def fetch(url: str):
    with sync_playwright() as playwright:
        browser = app_options.browser.get(playwright).launch(headless=app_options.headless and not app_options.debug)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        if app_options.headless:
            result = page.get_by_test_id("Headless-output").text_content()
        else:
            try:
                page.get_by_test_id("Headless-output").text_content(timeout=1000 * 60 * 60 * 24)
            except Error:
                result = "All done!"
        if not app_options.debug:
            browser.close()
    return result


@app.callback()
def main(
        recipe_url: str = typer.Option(..., "--url", "-u", help="A sharable ASP Chef URL"),
        headless: bool = typer.Option(False, help="Run ASP Chef in headless mode"),
        browser: Browser = typer.Option(Browser.FIREFOX, "--browser", help="Use a specific browser"),
        debug: bool = typer.Option(False, "--debug", help="Don't minimize browser"),
        version: bool = typer.Option(False, "--version", callback=version_callback, is_eager=True,
                                     help="Print version and exit"),
):
    """
    A simple CLI to run ASP Chef
    """
    global app_options

    if headless:
        if "/headless#" not in recipe_url:
            recipe_url = recipe_url.replace("/#", "/headless#", 1)
        validate("headless mode", recipe_url, contains="/headless#",
                 help_msg="Invalid URL. Not a sharable ASP Chef URL.")

    app_options = AppOptions(
        recipe_url=recipe_url,
        headless=headless,
        browser=browser,
        debug=debug,
    )


@app.command(name="run")
def command_run() -> None:
    """
    Run a recipe.
    """
    with console.status("Processing..."):
        result = fetch(app_options.recipe_url)

    console.print(result)


@app.command(name="run-with")
def command_run_with(
        the_input: str = typer.Option("--", "--input", "-i",
                                      help="A custom input for the recipe (read from STDIN by default; "
                                           "use CTRL+D to close the input)"),
) -> None:
    """
    Run a recipe with the input specified from STDIN or via the --input option.
    """
    if the_input == "--":
        the_input = ''.join(line for line in fileinput.input("-"))

    url = app_options.recipe_url
    if not app_options.headless:
        url = url.replace("/#", "/open#", 1)
    url = url.replace(r"#.*;", "#", 1)
    url = url.replace("#", "#" + compress_object_for_url({"input": the_input}, suffix="") + ";", 1)

    with console.status("Processing..."):
        result = fetch(url)

    console.print(result)
