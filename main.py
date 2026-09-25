from dify_plugin import DifyPluginEnv, Plugin

# 120 s por llamada: una búsqueda deep tarda cerca de un minuto; el cliente corta antes (typesearch_plugin.api).
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == "__main__":
    plugin.run()
