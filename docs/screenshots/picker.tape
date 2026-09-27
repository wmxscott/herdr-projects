# The README screenshots. Run `scripts/demo --vhs` rather than this tape
# directly: it seeds a made-up registry, builds the isolated environment the
# tape expects, and runs it once per theme with that theme's `Set Theme` first.

Require herdr-projects
Require fzf

Set Shell "bash"
Set FontFamily "FiraCode Nerd Font"
Set FontSize 18
Set LineHeight 1.25
Set Width 1000
Set Height 660
Set Padding 24
Set TypingSpeed 0

Hide
Type "clear && herdr-projects picker"
Enter
Wait+Screen@10s /dotfiles/
# Down to work/api, the workspace you're in.
Down 8
Sleep 1s
Show
Screenshot picker.png
Sleep 500ms
