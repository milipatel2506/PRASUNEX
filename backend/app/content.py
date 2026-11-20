"""Content library: teacher action plans and parent messages (English, Gujarati, Hindi).

Used by the template engine, which is the always-available fallback for the AI layer.
Messages avoid gendered verbs so they read correctly for any student.
"""

LANGS = {"en": "English", "gu": "Gujarati", "hi": "Hindi"}

SUBJECT_NAME = {
    "maths": {"en": "Maths", "gu": "ગણિત", "hi": "गणित"},
    "science": {"en": "Science", "gu": "વિજ્ઞાન", "hi": "विज्ञान"},
    "english": {"en": "English", "gu": "અંગ્રેજી", "hi": "अंग्रेज़ी"},
    "social": {"en": "Social Science", "gu": "સામાજિક વિજ્ઞાન", "hi": "सामाजिक विज्ञान"},
    "language": {"en": "Language", "gu": "ભાષા", "hi": "भाषा"},
}

TOPICS = {
    "maths": ["fractions and ratios", "algebraic expressions", "word problems"],
    "science": ["force and motion", "cells and tissues", "chemical reactions"],
    "english": ["reading comprehension", "grammar and tenses", "paragraph writing"],
    "social": ["map skills", "the Constitution", "the industrial revolution"],
    "language": ["grammar basics", "reading passages", "letter writing"],
}

# Teacher actions: reason group -> list of (kind, text). {subject}, {t0}, {t1} are filled in.
ACTIONS = {
    "attendance": [
        ("parent_contact", "Call or meet the family this week to understand the reasons for absence."),
        ("peer_support", "Pair the student with a classmate who shares notes for missed lessons."),
        ("progress_check", "Track attendance daily for two weeks and review on day 14."),
    ],
    "marks": [
        ("remedial_session", "Run a 15-minute catch-up session on {subject} ({t0}) within 3 days."),
        ("practice_test", "Give 5 short practice questions on {t1} and mark them personally."),
        ("progress_check", "Re-test {subject} ({t0}) in 10 days to check progress."),
    ],
    "homework": [
        ("homework_checklist", "Break homework into small tasks with a daily checklist."),
        ("progress_check", "Check submission every morning and praise on-time work."),
        ("parent_contact", "Ask parents to sign the homework diary for two weeks."),
    ],
    "incidents": [
        ("counselling", "Hold a calm, private talk to understand what is behind the behaviour."),
        ("goal_setting", "Set one clear, achievable goal and praise progress daily."),
        ("counselling", "Involve the school counsellor if incidents continue."),
    ],
    "volatile": [
        ("practice_test", "Offer a relaxed practice test to find out whether stress or specific topics are the cause."),
        ("remedial_session", "Revisit the topics where scores dropped most, in short sessions."),
        ("progress_check", "Compare the next two test scores and review with the student."),
    ],
}
REASON_GROUP = {"attendance": "attendance", "marks_falling": "marks", "low_marks": "marks",
                "volatile": "volatile", "homework": "homework", "incidents": "incidents"}

# Parent message pieces ----------------------------------------------------------------
GREETING = {"en": "Dear Parent,", "gu": "પ્રિય વાલીશ્રી,", "hi": "प्रिय अभिभावक,"}

REASON_CLAUSE = {
    "attendance": {"en": "attendance has been low",
                   "gu": "શાળામાં હાજરી ઓછી રહી છે",
                   "hi": "स्कूल में उपस्थिति कम रही है"},
    "marks_falling": {"en": "marks have been dropping in tests",
                      "gu": "પરીક્ષાઓમાં ગુણ ઘટતા જાય છે",
                      "hi": "परीक्षाओं में अंक घटते जा रहे हैं"},
    "low_marks": {"en": "marks are below the pass level in some subjects",
                  "gu": "કેટલાક વિષયોમાં ગુણ પાસ થવાના સ્તરથી નીચે છે",
                  "hi": "कुछ विषयों में अंक उत्तीर्ण स्तर से नीचे हैं"},
    "volatile": {"en": "test scores have been up and down",
                 "gu": "પરીક્ષાના ગુણમાં ઘણો ફેરફાર જોવા મળે છે",
                 "hi": "परीक्षा के अंकों में काफ़ी उतार-चढ़ाव दिख रहा है"},
    "homework": {"en": "homework has not been submitted on time",
                 "gu": "હોમવર્ક સમયસર જમા થયું નથી",
                 "hi": "होमवर्क समय पर जमा नहीं हो रहा है"},
    "incidents": {"en": "there have been some behaviour concerns in class",
                  "gu": "વર્ગમાં વર્તન અંગે કેટલીક ચિંતાઓ નોંધાઈ છે",
                  "hi": "कक्षा में व्यवहार को लेकर कुछ चिंताएँ दर्ज हुई हैं"},
}

SCHOOL_ACTION = {
    "attendance": {"en": "we will check in with {name} daily and share notes for missed lessons",
                   "gu": "અમે {name} સાથે રોજ સંપર્કમાં રહીશું અને ગેરહાજરીના પાઠોની નોંધ આપીશું",
                   "hi": "हम {name} से रोज़ संपर्क में रहेंगे और छूटे पाठों के नोट्स देंगे"},
    "marks": {"en": "we will run extra help sessions for {name} in {subject}",
              "gu": "અમે {name} માટે {subject}માં વધારાના સહાય વર્ગો ચલાવીશું",
              "hi": "हम {name} के लिए {subject} में अतिरिक्त सहायता कक्षाएँ चलाएँगे"},
    "homework": {"en": "we will help {name} break homework into small daily tasks",
                 "gu": "અમે {name}ને હોમવર્કને નાના રોજિંદા કાર્યોમાં વહેંચવામાં મદદ કરીશું",
                 "hi": "हम {name} को होमवर्क छोटे-छोटे रोज़ के कामों में बाँटने में मदद करेंगे"},
    "incidents": {"en": "the class teacher will have a supportive one-to-one talk with {name}",
                  "gu": "વર્ગશિક્ષક {name} સાથે સહાનુભૂતિપૂર્વક વ્યક્તિગત વાત કરશે",
                  "hi": "कक्षा शिक्षक {name} से सहानुभूति के साथ अलग से बात करेंगे"},
    "volatile": {"en": "we will give {name} relaxed practice tests to build confidence",
                 "gu": "અમે {name}નો આત્મવિશ્વાસ વધારવા માટે શાંત વાતાવરણમાં અભ્યાસ કસોટીઓ લઈશું",
                 "hi": "हम {name} का आत्मविश्वास बढ़ाने के लिए आराम के माहौल में अभ्यास परीक्षाएँ लेंगे"},
}

HOME_ACTION = {
    "attendance": {"en": "please help {name} reach school on time every day and tell us if there is a problem",
                   "gu": "કૃપા કરીને {name}ને રોજ સમયસર શાળાએ મોકલો અને કોઈ મુશ્કેલી હોય તો અમને જણાવો",
                   "hi": "कृपया {name} को रोज़ समय पर स्कूल भेजें और कोई समस्या हो तो हमें बताएँ"},
    "marks": {"en": "please set aside 20 minutes each evening for {name} to revise {subject}",
              "gu": "કૃપા કરીને રોજ સાંજે 20 મિનિટ {name} પાસે {subject}નું પુનરાવર્તન કરાવો",
              "hi": "कृपया रोज़ शाम 20 मिनट {name} से {subject} का दोहराव करवाएँ"},
    "homework": {"en": "please check {name}'s homework diary every evening",
                 "gu": "કૃપા કરીને રોજ સાંજે {name}ની હોમવર્ક ડાયરી જુઓ",
                 "hi": "कृपया रोज़ शाम {name} की होमवर्क डायरी देखें"},
    "incidents": {"en": "please talk to {name} calmly about school and let us know of any worries",
                  "gu": "કૃપા કરીને {name} સાથે શાળા વિશે શાંતિથી વાત કરો અને કોઈ ચિંતા હોય તો અમને જણાવો",
                  "hi": "कृपया {name} से स्कूल के बारे में शांति से बात करें और कोई चिंता हो तो हमें बताएँ"},
    "volatile": {"en": "please encourage {name} to stay relaxed and revise a little every day",
                 "gu": "કૃપા કરીને {name}ને શાંત રહેવા પ્રોત્સાહિત કરો અને રોજ થોડું વાંચન કરાવો",
                 "hi": "कृपया {name} को शांत रहने के लिए प्रोत्साहित करें और रोज़ थोड़ा पढ़ाई करवाएँ"},
}

BODY = {
    "en": ("{greeting}\n\nWe are writing about {name}. Recently, {reasons}. This is something we can fix together, "
           "and we are acting early.\n\nAt school: {school_action}.\nAt home: {home_action}.\n\n"
           "Please speak to the class teacher if you would like to discuss this. We are here to help.\n\n"
           "- Class Teacher, {cls}"),
    "gu": ("{greeting}\n\nઅમે {name} વિશે જણાવવા માંગીએ છીએ. તાજેતરમાં {reasons}. આ બાબત આપણે સાથે મળીને સુધારી શકીએ છીએ, "
           "અને અમે વહેલી શરૂઆત કરી રહ્યા છીએ.\n\nશાળામાં: {school_action}.\nઘરે: {home_action}.\n\n"
           "જો તમે આ અંગે વાત કરવા માંગતા હો, તો કૃપા કરીને વર્ગશિક્ષકનો સંપર્ક કરો. અમે મદદ માટે અહીં છીએ.\n\n"
           "- વર્ગશિક્ષક, {cls}"),
    "hi": ("{greeting}\n\nहम {name} के बारे में बताना चाहते हैं। हाल में {reasons}। यह बात हम मिलकर सुधार सकते हैं, "
           "और हम जल्दी कदम उठा रहे हैं।\n\nस्कूल में: {school_action}।\nघर पर: {home_action}।\n\n"
           "यदि आप इस बारे में बात करना चाहें, तो कृपया कक्षा शिक्षक से संपर्क करें। हम मदद के लिए यहाँ हैं।\n\n"
           "- कक्षा शिक्षक, {cls}"),
}
AND = {"en": " and ", "gu": " અને ", "hi": " और "}


def subject_label(key: str, lang: str = "en") -> str:
    """Display name for a subject key. Built-in subjects are translated; a faculty-added subject ('x:Name') keeps its own name."""
    if key in SUBJECT_NAME:
        return SUBJECT_NAME[key][lang]
    return key[2:] if key.startswith("x:") else key


def subject_topics(key: str) -> list[str]:
    if key in TOPICS:
        return TOPICS[key]
    n = subject_label(key)
    return [f"recent {n} classwork", f"key ideas in {n}", f"{n} practice questions"]
