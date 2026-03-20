# Overriding PyAION modules

If you want to temporarily override a pyaion module, you should:

1. Paste the module into this folder
2. Edit `repository/__init__.py` to add your module to the list of overrides

Don't go around editing `import` statements! There's no need, and you'll bypass
the automatic warnings that get recorded when things are overridden
