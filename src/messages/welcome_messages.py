"""Welcome message templates for clan additions."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get clan names from environment
CLAN1_NAME = os.getenv("CLAN1_NAME", "Clan 1")
CLAN2_NAME = os.getenv("CLAN2_NAME", "Clan 2")

def get_welcome_message(clan_name: str) -> str:
    """
    Get the welcome message for a specific clan.
    
    Args:
        clan_name: The name of the clan
        
    Returns:
        str: The formatted welcome message
    """
    # Default message template
    default_message = (
        f"🎉 Welcome to {clan_name}!\n\n"
        f"You have been successfully added to the clan and received all necessary roles.\n"
        f"If you have any questions, feel free to ask the officers."
    )
    
    # Specific messages for each clan
    messages = {
        CLAN1_NAME: (
            ":crescent_moon: **Welcome to Requiem Moon** :crescent_moon:\n"
            "Welcome to **Requiem Moon**, the **HARDCORE** guild of Requiem.\n"
            "Please take a moment to carefully follow the steps below – this information is crucial for your onboarding.\n\n"
            "---\n\n"
            ":scroll: **Steps to Get Started:**\n\n"
            ":one: **Read the Guild Rules:**\n"
            "The guild rules (which include the Requiem community rules) can be found here:\n"
            "https://discord.com/channels/229323181729513473/1327611688853442610/1327621563863793674\n\n"
            ":two: **Sign Up for Guild Events:**\n"
            "Event participation is **mandatory**. You can sign up here:\n"
            "• https://discord.com/channels/229323181729513473/1292858887690518579\n"
            "• https://discord.com/channels/229323181729513473/1305630589960847420\n"
            "• https://discord.com/channels/229323181729513473/1324339720804630620\n\n"
            ":three: **Complete the Following Forms:**\n"
            "• **Data Form (Moon Only):** https://discord.com/channels/229323181729513473/1308770178808676352/1315078759300468837\n"
            "• **Loot Preferences:** https://docs.google.com/forms/d/e/1FAIpQLSfv43t1RDTVFDz8h3ct-WOV5dNiaY81gB-tu-Bh7PeJwArPlg/viewform\n\n"
            ":four: **Important Notes:**\n"
            "• Ensure your **Discord name matches your in-game name** so members know who you are.\n"
            "• Join the **Alliance Discord** via this invite link: https://discord.com/channels/229323181729513473/1308770178808676352/1308771783834472489\n"
            "• Your initial status will be **Trial** for 2 weeks. At the end of this period, if you do not meet our criteria, you will unfortunately be removed from the guild.\n\n"
            "---\n\n"
            ":tada: **Welcome aboard!**\n"
            "We're excited to have you in Requiem Moon. Let's aim for greatness together!"
        ),
        CLAN2_NAME: (
            ":crescent_moon: **Welcome to Requiem Moon** :crescent_moon:\n"
            "Welcome to **Requiem Moon**, the **HARDCORE** guild of Requiem.\n"
            "Please take a moment to carefully follow the steps below – this information is crucial for your onboarding.\n\n"
            "---\n\n"
            ":scroll: **Steps to Get Started:**\n\n"
            ":one: **Read the Guild Rules:**\n"
            "The guild rules (which include the Requiem community rules) can be found here:\n"
            "https://discord.com/channels/229323181729513473/1327611688853442610/1327621563863793674\n\n"
            ":two: **Sign Up for Guild Events:**\n"
            "Event participation is **mandatory**. You can sign up here:\n"
            "• https://discord.com/channels/229323181729513473/1292858887690518579\n"
            "• https://discord.com/channels/229323181729513473/1305630589960847420\n"
            "• https://discord.com/channels/229323181729513473/1324339720804630620\n\n"
            ":three: **Complete the Following Forms:**\n"
            "• **Data Form (Moon Only):** https://discord.com/channels/229323181729513473/1308770178808676352/1315078759300468837\n"
            "• **Loot Preferences:** https://docs.google.com/forms/d/e/1FAIpQLSfv43t1RDTVFDz8h3ct-WOV5dNiaY81gB-tu-Bh7PeJwArPlg/viewform\n\n"
            ":four: **Important Notes:**\n"
            "• Ensure your **Discord name matches your in-game name** so members know who you are.\n"
            "• Join the **Alliance Discord** via this invite link: https://discord.com/channels/229323181729513473/1308770178808676352/1308771783834472489\n"
            "• Your initial status will be **Trial** for 2 weeks. At the end of this period, if you do not meet our criteria, you will unfortunately be removed from the guild.\n\n"
            "---\n\n"
            ":tada: **Welcome aboard!**\n"
            "We're excited to have you in Requiem Moon. Let's aim for greatness together!"
        )
    }
    
    # Return specific message if available, otherwise default message
    return messages.get(clan_name, default_message) 