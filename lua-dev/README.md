# Development plugins

Unsigned plugin bundles used while developing the scene Lua API.
They are not shipped with PrusaSlicer. To use one, symlink it into the
config directory and run *Plugins → Rescan*:

    ln -s "$(pwd)/lua-dev/com.soundgoof.scene" ~/.config/PrusaSlicer/lua/com.soundgoof.scene
