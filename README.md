# Jarvis Assistant

## Prerequisites

1. **Install Python**
   - Ensure Python 3.11 or higher is installed on your system. You can download it from [Python's official website](https://www.python.org/).

2. **Install Required Libraries**
   - Install the required Python libraries listed in `requirements.txt` using:
     ```cmd
     pip install -r requirements.txt
     ```

## Steps to Run the Project

1. **Configure the `.env` File** (Opitional)
   - Create a `.env` file in the root directory of the project.
   - Add the following variables:
     ```env
        USER_DISCORD_TOKEN=<token_of_your_account>
        JARVIS_TOKEN=<token_of_your_jarvis_account>
        DISCORD_CHANNEL_ID=<id_of_the_channel_that_jarvis_will_read>
        CHANNEL_<NAME>=<channel_id_you_share_with_someone>
     ```
   - `<token_of_your_account>` - discord token allowing to send messages from your account
   - `<token_of_your_jarvis_account>` - discord token allowing to send and read messages from jarvis' account
   - `<id_of_the_channel_that_jarvis_will_read>` - id of the channel that jarvis will read to recognize commands
   - `<channel_id_you_share_with_someone>` - channel id you share with someone. Jarvis needs this to send messages to this channel.
   - `<NAME>` - text
   You can add as many CHANNEL_<NAME> channels as you want, but <NAME> must be different each time.

2. **Run the Main Script**
   - Open a command prompt in the project directory.
   - Execute the main script to start the Jarvis assistant:
     ```cmd
     python core/main.py
     ```

## Functionalities

1. **Discord Integration**
   - The assistant can interact with Discord servers using the bot token provided in the `.env` file.
   - Commands include sending messages, searching YouTube, and more.

2. **Voice Commands**
   - Jarvis can process voice commands using the `speech_handler` module.
   - Ensure your microphone is configured correctly.

3. **Possibilities**
   - Look at the commands folder to check the possibilities.


## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   - If the application fails due to missing Python dependencies, ensure all required packages are installed using `pip install -r requirements.txt`.

2. **Environment Variables Not Set**
   - Ensure the `.env` file is correctly configured with all required variables.

3. **Python Version Compatibility**
   - Ensure you are using Python 3.11 or higher.

## Notes

- The application uses various modules located in the `api`, `commands`, `core`, and `readers` directories.
- Modify the `requirements.txt` as needed to include additional dependencies.

## Additional Information

- For more details on Python, visit [Python Documentation](https://docs.python.org/3/).
