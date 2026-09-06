# Grok prompts

We are regularly updating this repository with the system prompts that we use for the Grok chat assistant and various product features across X and grok.com.

## Prompts

All prompt files in this repository are listed below.

### Grok 4
* [`grok4_system_turn_prompt_v8.j2`](grok4_system_turn_prompt_v8.j2) - Main system prompt for the Grok 4 chat assistant on grok.com and X.
* [`grok_4_safety_prompt.txt`](grok_4_safety_prompt.txt) - Standalone safety policy prompt for Grok 4 (`grok-4-0709` model on the xAI API).

### Grok 4.1
* [`grok4p1_thinking_system_turn_prompt_v2.j2`](grok4p1_thinking_system_turn_prompt_v2.j2) - System prompt for Grok 4.1 in thinking mode.
* [`grok4p1_non_thinking_system_turn_prompt.j2`](grok4p1_non_thinking_system_turn_prompt.j2) - System prompt for Grok 4.1 in non-thinking mode (with tool access).
* [`grok4p1_non_thinking_no_tool_system_turn_prompt.j2`](grok4p1_non_thinking_no_tool_system_turn_prompt.j2) - System prompt for Grok 4.1 in non-thinking mode without tool access.

### Grok 4 Mini
* [`grok_4_mini_system_prompt.txt`](grok_4_mini_system_prompt.txt) - System prompt prefix for the Grok 4 Mini model (`grok-4-fast` on the xAI API).

### Grok 4 Code
* [`grok_4_code_rc1_safety_prompt.txt`](grok_4_code_rc1_safety_prompt.txt) - Safety policy prompt prefix for the Grok 4 Code release candidate (`grok-code-fast-1` on the xAI API).

### Grok 3
* [`grok3_official0330_p1.j2`](grok3_official0330_p1.j2) - Main system prompt for the Grok 3 chat assistant on grok.com and X.

### Features & Bots
* [`grok_analyze_button.j2`](grok_analyze_button.j2) - Prompt powering the "Grok Explain" / Analyze button feature on X and grok.com.
* [`ask_grok_system_prompt.j2`](ask_grok_system_prompt.j2) - System prompt governing the @grok bot on X.

## License
This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
