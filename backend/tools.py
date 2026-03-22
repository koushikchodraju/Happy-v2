generate_cad_prototype_tool = {
    "name": "generate_cad_prototype",
    "description": "Generates a 3D wireframe prototype based on a user's description. Use this when the user asks to 'visualize', 'prototype', 'create a wireframe', or 'design' something in 3D.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "The user's description of the object to prototype."
            }
        },
        "required": ["prompt"]
    }
}


write_file_tool = {
    "name": "write_file",
    "description": "Writes content to a file at the specified path. Overwrites if exists.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to write to."
            },
            "content": {
                "type": "STRING",
                "description": "The content to write to the file."
            }
        },
        "required": ["path", "content"]
    }
}

read_directory_tool = {
    "name": "read_directory",
    "description": "Lists the contents of a directory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the directory to list."
            }
        },
        "required": ["path"]
    }
}

read_file_tool = {
    "name": "read_file",
    "description": "Reads the content of a file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to read."
            }
        },
        "required": ["path"]
    }
}

system_control_tool = {
    "name": "system_control",
    "description": (
        "Controls the Windows operating system and HAPPY application. Use this for any OS-level or app-level action.\n"
        "Supported intents and actions:\n"
        "• system_power: lock, shutdown, restart, sleep, hibernate, cancel_shutdown\n"
        "• system_control: set_volume (value=0-100), volume_up, volume_down, mute, unmute, "
          "set_brightness (value=0-100), brightness_up, brightness_down\n"
        "• network_control: wifi_on, wifi_off, bluetooth_on, bluetooth_off\n"
        "• application_control: open_app (target=app name), close_app (target=app name), "
          "minimize_all, show_desktop, switch_window\n"
        "• system_query: get_time, get_battery, get_cpu_usage, get_ram_usage, get_storage, get_ip, get_wifi_status\n"
        "• utility: screenshot, open_folder (target=folder path), open_file (target=full file path), "
          "reveal_file (target=full file path — opens folder and highlights file), "
          "search (target=query), clipboard_set (value=text), clipboard_get, empty_recycle_bin\n"
        "• frontend_control: camera_on (activate/open/turn on camera), "
          "camera_off (deactivate/close/turn off camera), "
          "hand_gesture_on (enable/activate hand gesture/gesture mode/hand tracking), "
          "hand_gesture_off (disable/deactivate hand gesture mode)"
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "intent": {
                "type": "STRING",
                "description": (
                    "The intent category: system_power | system_control | network_control | "
                    "application_control | system_query | utility | frontend_control"
                )
            },
            "action": {
                "type": "STRING",
                "description": "The specific action to execute (e.g. 'lock', 'set_volume', 'open_app', 'camera_on', 'hand_gesture_on')"
            },
            "target": {
                "type": "STRING",
                "description": "Optional target entity (e.g. app name, folder path, search query)"
            },
            "value": {
                "type": "STRING",
                "description": "Optional value (e.g. '50' for volume level, '70' for brightness)"
            }
        },
        "required": ["intent", "action"]
    }
}

whatsapp_send_tool = {
    "name": "whatsapp_send",
    "description": (
        "Sends a WhatsApp message to a contact by name using the WhatsApp Desktop app. "
        "Use this when the user says things like 'send a WhatsApp message to [name] saying [message]', "
        "'WhatsApp [name] and say [message]', or 'message [name] on WhatsApp'. "
        "Extracts the contact name and the message text from the user's request."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "contact_name": {
                "type": "STRING",
                "description": "The name of the WhatsApp contact to send the message to."
            },
            "message": {
                "type": "STRING",
                "description": "The message text to send."
            }
        },
        "required": ["contact_name", "message"]
    }
}

tools_list = [{"function_declarations": [
    generate_cad_prototype_tool,
    write_file_tool,
    read_directory_tool,
    read_file_tool,
    system_control_tool,
    whatsapp_send_tool
]}]
