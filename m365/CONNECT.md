# Connecting to Grunt

The Grunt skills work through the Grunt connector: an MCP connection to Grunt.
In Microsoft 365 Copilot the Grunt plugin brings it, so there is no address to
enter. Each user signs in once, in the browser, with their own Grunt account.

Use these steps when you tell the user how to connect.

| App | Steps |
| --- | --- |
| Copilot Cowork | Open **Customize** from the left navigation, choose **Plugins** and open **Grunt**. If it is not under **Added**, add it from **Discover** or **Shared with me**. Start a request that needs Grunt and choose **Connect** when Cowork asks, then sign in with your Grunt account. |
| Copilot in PowerPoint | In the Copilot pane, choose **+** > **Manage plugins** and turn **Grunt** on. Choose **Connect** when Copilot asks, then sign in with your Grunt account. |
| Copilot Chat | Open **Plugins** in the left pane and add **Grunt**. Choose **Connect** when Copilot asks, then sign in with your Grunt account. |

If Grunt is not listed anywhere, the organization's Microsoft 365 administrator
has not made the plugin available to this user yet. Ask them to.

## Charts on slides in PowerPoint

Placing a chart on a slide of an open presentation also needs PowerPoint for
Windows with the Grunt add-in running and signed in to the same Grunt account.
The tool that lists the open presentations says whether Grunt is connected to
PowerPoint. Without the add-in, charts and tables can still be made and shown in
the conversation.

## More than one Grunt connector

An organization can have several, for example one for Grunt's cloud service and
one for a Grunt it runs itself or a test environment. Each is a separate Grunt
with its own assets and its own sign-in.

- The skills use the one the user names. If they name none, the one that is
  signed in; if several are signed in, the one called just "Grunt"; otherwise
  they ask.
- They don't ask the user to sign in to a second one while one works.
- They keep to one connector for a whole deck or report, so every asset is in
  the same Grunt.

Some apps load a newly connected plugin's tools only in a new conversation.
