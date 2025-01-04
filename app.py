from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_cors import CORS
import os
import pandas as pd
import re
import tempfile
from difflib import get_close_matches

# Add the new UnitNameCorrector class
class UnitNameCorrector:
    def __init__(self):
        self.valid_units = {
            'הנדסה',
            'מאב',
            'מהן',
            'מעמ',
            'מתן',
            'מטס',
            'תשתיות'
        }
        
        self.common_variations = {
            'מת"ן': 'מתן',
            'מא״ב': 'מאב',
            'מה״ןו': 'מהן',
            'מתןןן': 'מתן',
            'מתנ': 'מתן',
            'הנדס': 'הנדסה',
            'הנדסת': 'הנדסה',
            'הנדסהה': 'הנדסה',
            'מאבב': 'מאב',
            'מ"א"ב': 'מאב',
            'מהנ': 'מהן',
            'מהןן': 'מהן',
            'מעממ': 'מעמ',
            'מעם': 'מעמ',
            'מטסס': 'מטס',
            'תשתית': 'תשתיות',
            'תשתיותת': 'תשתיות'
        }

    def find_possible_matches(self, unit_name, cutoff=0.6):
        """מוצא את כל ההתאמות האפשריות עם ציון הדמיון שלהן"""
        if not isinstance(unit_name, str):
            return []

        cleaned_name = re.sub(r'["""]', '', unit_name.strip())
        matches = []
        
        # בדיקת התאמות במילון השגיאות הנפוצות
        if cleaned_name in self.common_variations:
            matches.append((self.common_variations[cleaned_name], 1.0))  # ציון 1.0 להתאמה מדויקת
            
        # חיפוש התאמות מבוססות דמיון מחרוזות
        for valid_unit in self.valid_units:
            similarity = self.calculate_similarity(cleaned_name, valid_unit)
            if similarity >= cutoff:
                matches.append((valid_unit, similarity))
        
        # מיון לפי ציון הדמיון בסדר יורד
        return sorted(matches, key=lambda x: x[1], reverse=True)

    def calculate_similarity(self, str1, str2):
        """מחשב את מידת הדמיון בין שתי מחרוזות"""
        max_len = max(len(str1), len(str2))
        if max_len == 0:
            return 0
        
        # חישוב מרחק לוונשטיין
        distance = self.levenshtein_distance(str1, str2)
        return 1 - (distance / max_len)

    def levenshtein_distance(self, str1, str2):
        """מחשב את מרחק לוונשטיין בין שתי מחרוזות"""
        if len(str1) < len(str2):
            return self.levenshtein_distance(str2, str1)

        if len(str2) == 0:
            return len(str1)

        previous_row = range(len(str2) + 1)
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def correct_unit_name(self, unit_name):
        """מתקן שם יחידה עם טיפול במקרים של דו-משמעות"""
        if not isinstance(unit_name, str):
            return unit_name

        # מציאת כל ההתאמות האפשריות
        matches = self.find_possible_matches(unit_name)
        
        if not matches:
            return unit_name
            
        # אם יש יותר מהתאמה אחת עם ציון דמיון קרוב
        close_matches = [m for m in matches if abs(m[1] - matches[0][1]) < 0.1]
        
        if len(close_matches) > 1:
            possible_units = [m[0] for m in close_matches]
            print(f'אזהרה: נמצאו מספר אפשרויות תיקון ל-"{unit_name}":')
            for unit, score in close_matches:
                print(f'- {unit} (ציון דמיון: {score:.2%})')
            # במקרה של ספק, נחזיר את ההתאמה הטובה ביותר אבל נציג אזהרה
            return close_matches[0][0]
        
        # אם יש התאמה ברורה אחת
        corrected = matches[0][0]
        if corrected != unit_name:
            print(f'טעות איות נמצאה: {unit_name}, תיקון: {corrected} (ציון דמיון: {matches[0][1]:.2%})')
        return corrected

    def correct_ratings_string(self, ratings_string):
        """מתקן את שמות היחידות בכל מחרוזת הדירוגים"""
        if not isinstance(ratings_string, str):
            return ratings_string
            
        corrected_lines = []
        for line in ratings_string.split('\n'):
            match = re.match(r"(.*?)\((\d+)\)", line.strip())
            if match:
                unit_name = match.group(1).strip()
                rating = match.group(2)
                corrected_name = self.correct_unit_name(unit_name)
                corrected_lines.append(f"{corrected_name}({rating})")
            else:
                corrected_lines.append(line)
                
        return '\n'.join(corrected_lines)
    
def process_excel_with_correction(df):
    """Process the Excel dataframe and correct unit names."""
    corrector = UnitNameCorrector()
    
    # Create a copy of the dataframe
    df_corrected = df.copy()
    
    # Apply correction to the 'יחידות ודירוגים' column
    df_corrected['יחידות ודירוגים'] = df_corrected['יחידות ודירוגים'].apply(
        corrector.correct_ratings_string
    )
    
    # If there's a 'יחידה מקדימה' column, correct those names too
    if 'יחידה מקדימה' in df_corrected.columns:
        df_corrected['יחידה מקדימה'] = df_corrected['יחידה מקדימה'].apply(
            corrector.correct_unit_name
        )
    
    return df_corrected

# Update the clean_and_sort_data function
def clean_and_sort_data(input_file, allocations, unit_weights):
    # Read the Excel file
    df = pd.read_excel(input_file)
    
    # Apply the correction before processing
    df = process_excel_with_correction(df)
    
    cleaned_data = []
    assignments = []
    assigned_soldiers = set()

    # Track unit-level averages
    unit_averages = {unit: [] for unit in allocations.keys()}

    # First, handle pre-assigned soldiers
    pre_assigned_soldiers = df[df['שיבוץ מקדים'] == 'כן']
    for _, row in pre_assigned_soldiers.iterrows():
        soldier_name = row['שם החייל']
        city = row['עיר מגורים']
        pre_assigned_unit = row['יחידה מקדימה']
        
        # Find the soldier's rating for the pre-assigned unit
        unit_ratings = row['יחידות ודירוגים']
        soldier_unit_rating = None
        soldier_priority = None
        
        for priority, unit_rating in enumerate(unit_ratings.split('\n'), start=1):
            match = re.match(r"(.*)\((\d+)\)", unit_rating)
            if match:
                unit_name = match.group(1).strip()
                unit_score = int(match.group(2))
                if unit_name == pre_assigned_unit:
                    soldier_unit_rating = unit_score
                    soldier_priority = priority
                    break
        
        soldier_unit_rating = soldier_unit_rating if soldier_unit_rating is not None else 1
        soldier_priority = soldier_priority if soldier_priority is not None else len(unit_ratings.split('\n'))
        
        if allocations.get(pre_assigned_unit, 0) > 0 and soldier_name not in assigned_soldiers:
            # Calculate unit and soldier weights
            unit_weight = unit_weights.get(pre_assigned_unit, 80)
            soldier_weight = 100 - unit_weight
            weight_unit = unit_weight / 100
            weight_soldier = soldier_weight / 100
            
            average_score = (weight_unit * soldier_unit_rating) + (weight_soldier * (8 - soldier_priority))
            
            assignment_entry = {
                'שם החייל': soldier_name,
                'עיר מגורים': city,
                'יחידה': pre_assigned_unit,
                'דירוג החייל': 8 - soldier_priority,
                'דירוג היחידה': soldier_unit_rating,
                'אחוז השפעה יחידה': unit_weight,
                'אחוז השפעה חייל': soldier_weight,
                'ממוצע': average_score
            }
            
            assignments.append(assignment_entry)
            unit_averages[pre_assigned_unit].append(soldier_unit_rating)
            
            allocations[pre_assigned_unit] -= 1
            assigned_soldiers.add(soldier_name)

    # Remove pre-assigned soldiers from the main dataframe
    df = df[~df['שם החייל'].isin(assigned_soldiers)]

    # Continue with existing assignment logic for remaining soldiers
    for _, row in df.iterrows():
        soldier_name = row['שם החייל']
        city = row['עיר מגורים']
        unit_ratings = row['יחידות ודירוגים']
        unit_rating_pairs = unit_ratings.split('\n')

        for priority, unit_rating in enumerate(unit_rating_pairs, start=1):
            match = re.match(r"(.*)\((\d+)\)", unit_rating)
            if match:
                unit_name = match.group(1).strip()
                unit_score = int(match.group(2))
                
                # Use unit-specific weight if available, otherwise default to 80%
                unit_weight = unit_weights.get(unit_name, 80)
                soldier_weight = 100 - unit_weight
                weight_unit = unit_weight / 100
                weight_soldier = soldier_weight / 100
                
                average_score = (weight_unit * unit_score) + (weight_soldier * (8 - priority))
                
                entry = {
                    'שם החייל': soldier_name,
                    'עיר מגורים': city,
                    'יחידה': unit_name,
                    'דירוג החייל': 8 - priority,
                    'דירוג היחידה': unit_score,
                    'אחוז השפעה יחידה': unit_weight,
                    'אחוז השפעה חייל': soldier_weight,
                    'ממוצע': average_score
                }
                
                cleaned_data.append(entry)

    # Sort and process assignments
    cleaned_df = pd.DataFrame(cleaned_data)
    cleaned_df = cleaned_df.sort_values(by='ממוצע', ascending=False)

    total_rounds = max(allocations.values())
    for round_number in range(total_rounds):
        used_units = set()
        for _, row in cleaned_df.iterrows():
            soldier_name = row['שם החייל']
            city = row['עיר מגורים']
            unit_name = row['יחידה']
            soldier_rating = row['דירוג החייל']
            unit_rating = row['דירוג היחידה']
            unit_weight = row['אחוז השפעה יחידה']
            soldier_weight = row['אחוז השפעה חייל']
            average_score = row['ממוצע']
            
            if (allocations.get(unit_name, 0) > 0 and 
                unit_name not in used_units and 
                soldier_name not in assigned_soldiers):
                
                assignment_entry = {
                    'שם החייל': soldier_name,
                    'עיר מגורים': city,
                    'יחידה': unit_name,
                    'דירוג החייל': soldier_rating,
                    'דירוג היחידה': unit_rating,
                    'אחוז השפעה יחידה': unit_weight,
                    'אחוז השפעה חייל': soldier_weight,
                    'ממוצע': average_score
                }
                
                assignments.append(assignment_entry)
                unit_averages[unit_name].append(unit_rating)
                
                allocations[unit_name] -= 1
                used_units.add(unit_name)
                assigned_soldiers.add(soldier_name)
        
        # Remove assigned soldiers from the dataframe
        cleaned_df = cleaned_df[~cleaned_df['שם החייל'].isin(assigned_soldiers)]
        
        if cleaned_df.empty:
            break

    # Add unit average to each assignment
    for assignment in assignments:
        unit_name = assignment['יחידה']
        assignment['ממוצע יחידה'] = (sum(unit_averages[unit_name]) / len(unit_averages[unit_name])) if unit_averages[unit_name] else 0

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    assignments_df = pd.DataFrame(assignments)
    assignments_df.to_excel(temp_file.name, index=False)

    return assignments, temp_file.name

app = Flask(__name__)
CORS(app)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Extract unit weights
        unit_weights = {
            'הנדסה': float(request.form['weight_unit_הנדסה']),
            'מאב': float(request.form['weight_unit_מאב']),
            'מהן': float(request.form['weight_unit_מהן']),
            'מעמ': float(request.form['weight_unit_מעמ']),
            'מתן': float(request.form['weight_unit_מתן']),
            'מטס': float(request.form['weight_unit_מטס']),
            'תשתיות': float(request.form['weight_unit_תשתיות'])
        }

        allocations = {
            'הנדסה': int(request.form['הנדסה']),
            'מאב': int(request.form['מאב']),
            'מהן': int(request.form['מהן']),
            'מעמ': int(request.form['מעמ']),
            'מתן': int(request.form['מתן']),
            'מטס': int(request.form['מטס']),
            'תשתיות': int(request.form['תשתיות'])
        }

        file = request.files['file']
        if file:
            input_file = os.path.join('uploads', file.filename)
            os.makedirs('uploads', exist_ok=True)
            file.save(input_file)

            assignments, temp_file_path = clean_and_sort_data(input_file, allocations, unit_weights)
            return render_template('index.html', assignments=assignments, temp_file=temp_file_path)

    return render_template('index.html')

@app.route('/download', methods=['GET'])
def download_file():
    temp_file = request.args.get('path')
    if temp_file and os.path.exists(temp_file):
        return send_file(temp_file, as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)
