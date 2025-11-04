"""
SQL generation module for creating database statements from parsed loot data.
"""

from .config import QUALITY_LABELS, PROFESSION_SKILL_ID
from .enricher import decide_drop_chance


class SQLGenerator:
    """Generates SQL blocks from NPC loot data."""

    @staticmethod
    def generate_loot_sql(npc_id, items, npc_name=None, lootmode=23, groupid=0, mincount=1, maxcount=1, shared=0):
        """
        Generate SQL REPLACE and conditions blocks for NPC loot.
        
        Args:
            npc_id: Numeric NPC ID
            items: List of enriched item dicts
            npc_name: Human-readable NPC name (uses ID if None)
            lootmode: Loot mode value for SQL (default 23)
            groupid: Group ID for SQL (default 0)
            mincount: Min count value for SQL (default 1)
            maxcount: Max count value for SQL (default 1)
            shared: Shared value for SQL (default 0)
            
        Returns:
            String containing comment block and SQL statements
        """
        if not npc_name:
            npc_name = str(npc_id)

        comment_lines = [f"/* NPC {npc_id} - {npc_name} loot list"]
        vals = []
        skipped = []

        # Process each item
        for it in items:
            iid = it['id']
            chance = decide_drop_chance(it)

            if chance is None:
                skipped.append(iid)
                continue

            # Build comment for this item
            comment_parts = SQLGenerator._build_item_comment_parts(it, chance)
            comment = f"{iid}"

            if comment_parts:
                comment += " -- " + " -- ".join(comment_parts)

            comment_lines.append(comment)

            # Format chance for SQL
            chance_sql = SQLGenerator._format_chance_for_sql(chance)

            vals.append(f"(@NPC,{iid},{chance_sql},{lootmode},{groupid},{mincount},{maxcount},{shared})")

        comment_lines.append("*/\n")

        sql_lines = []
        sql_lines.append(f"SET @NPC := {npc_id};")
        sql_lines.append("REPLACE INTO creature_loot_template (`entry`,`item`,`ChanceOrQuestChance`,`lootmode`,`groupid`,`mincountOrRef`,`maxcount`,`shared`) VALUES")

        if skipped:
            print(f"[!] Skipping {len(skipped)} items with no NPC-provided drop chance: {skipped}")

        sql_lines.append(",\n".join(vals) + ";")

        # Generate loot conditions for recipe items
        condition_sql = SQLGenerator._generate_condition_sql(npc_id, items)

        if condition_sql:
            sql_lines.append(condition_sql)

        return "\n".join(comment_lines + sql_lines)

    @staticmethod
    def _build_item_comment_parts(item, chance):
        """
        Build comment parts for a single item.
        
        Args:
            item: Item dict
            chance: Computed drop chance
            
        Returns:
            List of comment strings
        """
        parts = []

        # Include computed NPC drop chance
        try:
            fval = float(chance)

            if abs(fval - round(fval)) < 1e-9:
                parts.append(f"chance:{int(round(fval))}%")
            else:
                parts.append(f"chance:{round(fval, 2)}%")
        except (ValueError, TypeError):
            pass

        # Mark quest items
        if item.get('is_quest'):
            parts.append('quest')

        # Quality label
        q = int(item.get('quality', 0) or 0)
        qlabel = QUALITY_LABELS.get(q, f'q{q}')

        parts.append(f"quality:{qlabel}")

        # Recipe / profession
        if item.get('is_recipe'):
            prof = item.get('profession') or 'unknown'
            
            parts.append(f"{prof} (recipe)")

        # Item name
        parts.append(f"name:{item.get('name')}")

        return parts

    @staticmethod
    def _format_chance_for_sql(chance):
        """
        Format drop chance for SQL: integer if whole number, else up to 2 decimals.
        
        Args:
            chance: Float chance value
            
        Returns:
            String formatted for SQL
        """
        if abs(chance - round(chance)) < 1e-9:
            return str(int(round(chance)))
        else:
            return ('{:.2f}'.format(chance)).rstrip('0').rstrip('.')

    @staticmethod
    def _generate_condition_sql(npc_id, items):
        """
        Generate SQL conditions for profession recipes.
        
        Creates DELETE and INSERT statements for profession requirement conditions.
        
        Args:
            npc_id: Numeric NPC ID
            items: List of enriched item dicts
            
        Returns:
            SQL string or empty string if no conditions needed
        """
        # Find recipe items with profession
        recipe_items = [
            it for it in items
            if it.get('is_recipe') and it.get('profession') and it.get('id')
        ]

        # Filter to those with known profession skill IDs
        recipe_with_spell = [
            (it['id'], it['profession'])
            for it in recipe_items
            if PROFESSION_SKILL_ID.get(it['profession'])
        ]

        if not recipe_with_spell:
            return ""

        sql_lines = []
        ids = ",".join(str(i) for i, _ in recipe_with_spell)
        
        sql_lines.append("\n-- loot conditions")
        sql_lines.append(
            f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=1\n"
            f"    AND `SourceGroup`=@NPC\n"
            f"    AND `SourceEntry` IN ({ids}); -- item IDs"
        )
        sql_lines.append(
            "INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, "
            "`SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, "
            "`ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, "
            "`ErrorTextId`, `ScriptName`, `Comment`) VALUES"
        )

        cond_vals = []
        
        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SKILL_ID.get(prof)

            # Has profession condition (ConditionType 7 using profession spell id)
            cond_vals.append(
                f"(1, @NPC, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', "
                f"'Item Drop - Has {prof.capitalize()}')"
            )

            # No-item fallback condition (ConditionType 2 pointing at item)
            cond_vals.append(
                f"(1, @NPC, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', "
                f"'Item Drop - No Item')"
            )

        sql_lines.append(",\n".join(cond_vals) + ";")

        return "\n".join(sql_lines)
